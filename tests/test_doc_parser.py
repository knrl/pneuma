"""Tests for core.ingestion.doc_parser — on-demand document import."""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.ingestion.doc_parser import (
    DocType,
    detect_doc_type,
    import_content,
    parse_chat_log,
    parse_markdown_sections,
    parse_plain_text,
    parse_slack_export,
)


# ── detect_doc_type ──────────────────────────────────────────────

class TestDetectDocType:
    def test_slack_json_export(self):
        data = json.dumps([
            {"user": "U1", "text": "hello", "ts": "1234"},
            {"user": "U2", "text": "world", "ts": "1235"},
        ])
        assert detect_doc_type(data, ".json") == DocType.CHAT_HISTORY

    def test_json_not_slack(self):
        data = json.dumps({"key": "value"})
        assert detect_doc_type(data, ".json") != DocType.CHAT_HISTORY

    def test_decision_keywords(self):
        text = "## Decision\nWe decided to use PostgreSQL for persistence."
        assert detect_doc_type(text) == DocType.DECISION

    def test_adr_keyword(self):
        text = "ADR-042: Use event sourcing for the audit log."
        assert detect_doc_type(text) == DocType.DECISION

    def test_chat_log_pattern(self):
        text = (
            "[2026-04-19 10:00] alice: how do we deploy?\n"
            "[2026-04-19 10:01] bob: run deploy.sh\n"
            "[2026-04-19 10:02] alice: thanks\n"
            "[2026-04-19 10:03] carol: also check the docs\n"
        )
        assert detect_doc_type(text) == DocType.CHAT_HISTORY

    def test_general_fallback(self):
        text = "This is some general documentation about the system."
        assert detect_doc_type(text) == DocType.GENERAL

    def test_decision_heading_context(self):
        text = "# ADR-001\n## Context\nWe need a database.\n## Decision\nPostgres."
        assert detect_doc_type(text) == DocType.DECISION


# ── parse_markdown_sections ──────────────────────────────────────

class TestParseMarkdownSections:
    def test_splits_by_headings(self):
        text = "## Setup\nInstall deps.\n\n## Deploy\nRun deploy.sh."
        sections = parse_markdown_sections(text)
        assert len(sections) == 2
        assert sections[0]["title"] == "Setup"
        assert "Install deps" in sections[0]["content"]
        assert sections[1]["title"] == "Deploy"

    def test_preamble_preserved(self):
        text = "Some intro text.\n\n## First\nBody."
        sections = parse_markdown_sections(text)
        assert len(sections) == 2
        assert sections[0]["title"] == "preamble"
        assert "intro text" in sections[0]["content"]

    def test_no_headings_single_section(self):
        text = "Just a paragraph of text with no headings."
        sections = parse_markdown_sections(text)
        assert len(sections) == 1
        assert sections[0]["title"] == ""

    def test_empty_text(self):
        assert parse_markdown_sections("") == []
        assert parse_markdown_sections("   ") == []

    def test_empty_section_skipped(self):
        text = "## Empty\n\n## HasContent\nSome content here."
        sections = parse_markdown_sections(text)
        assert len(sections) == 1
        assert sections[0]["title"] == "HasContent"


# ── parse_plain_text ─────────────────────────────────────────────

class TestParsePlainText:
    def test_paragraphs_split(self):
        text = (
            "First paragraph with enough content to pass the threshold.\n\n"
            "Second paragraph that is also long enough to be its own chunk."
        )
        sections = parse_plain_text(text)
        assert len(sections) == 2

    def test_short_paragraphs_merged(self):
        text = "Short.\n\nAlso short.\n\nThis is a longer paragraph that will anchor the merge."
        sections = parse_plain_text(text)
        # Short ones get merged
        assert len(sections) <= 2

    def test_empty_text(self):
        assert parse_plain_text("") == []


# ── parse_slack_export ───────────────────────────────────────────

class TestParseSlackExport:
    def test_basic_messages(self):
        data = json.dumps([
            {"user": "U1", "text": "hello world", "ts": "1234"},
            {"user": "U2", "text": "how are you?", "ts": "1235"},
        ])
        messages = parse_slack_export(data)
        assert len(messages) == 2
        assert messages[0].user == "U1"
        assert messages[0].text == "hello world"

    def test_bot_messages_skipped(self):
        data = json.dumps([
            {"user": "U1", "text": "real message", "ts": "1234"},
            {"subtype": "bot_message", "text": "bot says hi", "ts": "1235"},
        ])
        messages = parse_slack_export(data)
        assert len(messages) == 1

    def test_empty_text_skipped(self):
        data = json.dumps([
            {"user": "U1", "text": "", "ts": "1234"},
            {"user": "U2", "text": "hello", "ts": "1235"},
        ])
        messages = parse_slack_export(data)
        assert len(messages) == 1

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            parse_slack_export('{"not": "a list"}')

    def test_channel_defaults_to_import(self):
        data = json.dumps([{"user": "U1", "text": "hi", "ts": "1"}])
        messages = parse_slack_export(data)
        assert messages[0].channel == "import"


# ── parse_chat_log ───────────────────────────────────────────────

class TestParseChatLog:
    def test_timestamped_format(self):
        text = (
            "[2026-04-19 14:30] alice: How do we deploy?\n"
            "[2026-04-19 14:31] bob: Run deploy.sh\n"
        )
        messages = parse_chat_log(text)
        assert len(messages) == 2
        assert messages[0].user == "alice"
        assert "deploy" in messages[0].text.lower()

    def test_simple_format(self):
        text = "alice: Hello\nbob: Hi there\n"
        messages = parse_chat_log(text)
        assert len(messages) == 2
        assert messages[0].user == "alice"

    def test_empty_text(self):
        messages = parse_chat_log("")
        assert messages == []

    def test_timestamp_variants(self):
        text = "[2026/04/19 14:30] alice: msg1\n[2026-04-19T14:30:00] bob: msg2\n"
        messages = parse_chat_log(text)
        assert len(messages) == 2


# ── import_content (integration) ─────────────────────────────────

class TestImportContent:
    @patch("core.ingestion.doc_parser.inject_entry")
    @patch("core.ingestion.doc_parser.check_duplicate")
    def test_decision_doc(self, mock_dup, mock_inject):
        mock_dup.return_value = {"is_duplicate": False}
        mock_inject.return_value = {
            "entry_id": "e1",
            "collection": "decisions-architecture",
            "ingested_at": "2026-04-19T00:00:00",
        }

        text = "## Decision\nWe decided to use PostgreSQL.\n\n## Context\nWe need ACID."
        result = import_content(text, doc_type="decision")

        assert result["doc_type"] == "decision"
        assert result["entries_stored"] == 2
        assert result["errors"] == []
        assert mock_inject.call_count == 2

    @patch("core.ingestion.doc_parser.inject_entry")
    @patch("core.ingestion.doc_parser.check_duplicate")
    def test_duplicates_skipped(self, mock_dup, mock_inject):
        mock_dup.return_value = {"is_duplicate": True, "matches": []}

        text = "## Heading\nSome existing content."
        result = import_content(text, doc_type="general")

        assert result["entries_stored"] == 0
        assert result["duplicates_skipped"] == 1
        mock_inject.assert_not_called()

    @patch("core.ingestion.doc_parser.inject_stories")
    @patch("core.ingestion.doc_parser.extract_stories")
    @patch("core.ingestion.doc_parser.anonymize_messages")
    @patch("core.ingestion.doc_parser.filter_messages")
    def test_chat_history_runs_pipeline(
        self, mock_filter, mock_anon, mock_extract, mock_inject
    ):
        from chat_bot.preprocessing.noise_filter import BufferedMessage
        from chat_bot.preprocessing.story_extractor import Story

        msg = BufferedMessage(user="u", text="how to deploy?", channel="c", ts="1")
        mock_filter.return_value = [msg]
        mock_anon.return_value = [msg]
        mock_extract.return_value = [
            Story(problem="how to deploy?", solution="run deploy.sh")
        ]
        mock_inject.return_value = {"stored": 1, "errors": []}

        text = (
            "[2026-04-19 10:00] alice: how to deploy?\n"
            "[2026-04-19 10:01] bob: run deploy.sh\n"
            "[2026-04-19 10:02] alice: another question?\n"
            "[2026-04-19 10:03] carol: the answer\n"
        )
        result = import_content(text, doc_type="chat-history")

        assert result["doc_type"] == "chat-history"
        assert result["entries_stored"] == 1
        mock_filter.assert_called_once()
        mock_anon.assert_called_once()
        mock_extract.assert_called_once()
        mock_inject.assert_called_once()

    @patch("core.ingestion.doc_parser.inject_stories")
    @patch("core.ingestion.doc_parser.extract_stories")
    @patch("core.ingestion.doc_parser.anonymize_messages")
    @patch("core.ingestion.doc_parser.filter_messages")
    def test_slack_json_chat_import(
        self, mock_filter, mock_anon, mock_extract, mock_inject
    ):
        from chat_bot.preprocessing.noise_filter import BufferedMessage
        from chat_bot.preprocessing.story_extractor import Story

        msg = BufferedMessage(user="U1", text="how to fix the bug?", channel="import", ts="1")
        mock_filter.return_value = [msg]
        mock_anon.return_value = [msg]
        mock_extract.return_value = [
            Story(problem="how to fix the bug?", solution="check the logs")
        ]
        mock_inject.return_value = {"stored": 1, "errors": []}

        data = json.dumps([
            {"user": "U1", "text": "how to fix the bug?", "ts": "1"},
            {"user": "U2", "text": "check the logs", "ts": "2"},
        ])
        result = import_content(data, doc_type="chat-history")

        assert result["doc_type"] == "chat-history"
        assert result["entries_stored"] == 1

    @patch("core.ingestion.doc_parser.inject_entry")
    @patch("core.ingestion.doc_parser.check_duplicate")
    def test_wing_room_override(self, mock_dup, mock_inject):
        mock_dup.return_value = {"is_duplicate": False}
        mock_inject.return_value = {
            "entry_id": "e1",
            "collection": "custom-wing-room",
            "ingested_at": "2026-04-19T00:00:00",
        }

        text = "Some content about our custom topic."
        result = import_content(
            text, doc_type="general", wing="custom", room="topic"
        )

        assert result["entries_stored"] == 1
        call_kwargs = mock_inject.call_args[1]
        assert call_kwargs["metadata"]["wing"] == "custom"
        assert call_kwargs["metadata"]["room"] == "topic"

    def test_empty_content(self):
        result = import_content("")
        assert result["entries_stored"] == 0
