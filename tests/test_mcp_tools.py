"""Tests for MCP memory tools — wake_up, recall, search, save, overview, optimize.

Uses mocked palace adapter to avoid needing real MemPalace storage.
"""

import asyncio
from unittest.mock import patch, MagicMock

import pytest

from core.rag.retriever import RetrievalResult


def _run(coro):
    """Helper to run an async function synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ── wake_up ──────────────────────────────────────────────────────

class TestAgentWakeUp:
    @patch("mcp_server.tools.memory_tools._wake_up")
    def test_returns_identity_text(self, mock_wake):
        mock_wake.return_value = "I am Pneuma. I help engineering teams."
        from mcp_server.tools.memory_tools import wake_up

        result = _run(wake_up())
        assert "Pneuma" in result
        mock_wake.assert_called_once_with(wing=None)

    @patch("mcp_server.tools.memory_tools._wake_up")
    def test_scoped_to_wing(self, mock_wake):
        mock_wake.return_value = "Project Alpha context"
        from mcp_server.tools.memory_tools import wake_up

        result = _run(wake_up(wing="alpha"))
        assert "Alpha" in result
        mock_wake.assert_called_once_with(wing="alpha")

    @patch("mcp_server.tools.memory_tools._wake_up")
    def test_empty_returns_fallback(self, mock_wake):
        mock_wake.return_value = ""
        from mcp_server.tools.memory_tools import wake_up

        result = _run(wake_up())
        assert "No identity" in result


# ── recall ───────────────────────────────────────────────────────

class TestAgentRecall:
    @patch("mcp_server.tools.memory_tools._recall")
    def test_returns_context(self, mock_recall):
        mock_recall.return_value = "We use PostgreSQL for all services."
        from mcp_server.tools.memory_tools import recall

        result = _run(recall(wing="decisions", room="architecture"))
        assert "PostgreSQL" in result
        mock_recall.assert_called_once_with(wing="decisions", room="architecture", n_results=10)

    @patch("mcp_server.tools.memory_tools._recall")
    def test_empty_wing_passes_none(self, mock_recall):
        mock_recall.return_value = "everything"
        from mcp_server.tools.memory_tools import recall

        result = _run(recall())
        mock_recall.assert_called_once_with(wing=None, room=None, n_results=10)

    @patch("mcp_server.tools.memory_tools._recall")
    def test_empty_returns_message(self, mock_recall):
        mock_recall.return_value = ""
        from mcp_server.tools.memory_tools import recall

        result = _run(recall(wing="empty"))
        assert "No entries" in result


# ── search_memory ────────────────────────────────────────────────

class TestSearchMemory:
    @patch("mcp_server.tools.memory_tools._search")
    def test_returns_formatted_results(self, mock_search):
        mock_search.return_value = [
            RetrievalResult(
                content="Use PostgreSQL for persistence",
                collection="decisions-architecture",
                entry_id="e1",
                relevance_score=0.85,
                metadata={},
            )
        ]
        from mcp_server.tools.memory_tools import search_memory

        result = _run(search_memory("database"))
        assert "PostgreSQL" in result
        assert "decisions-architecture" in result

    @patch("mcp_server.tools.memory_tools._search")
    def test_no_results(self, mock_search):
        mock_search.return_value = []
        from mcp_server.tools.memory_tools import search_memory

        result = _run(search_memory("nonexistent"))
        assert "No relevant entries" in result or "No results" in result


# ── save_knowledge ───────────────────────────────────────────────

class TestSaveKnowledge:
    @patch("mcp_server.tools.memory_tools.inject_entry")
    @patch("mcp_server.tools.memory_tools._check_dup")
    def test_saves_and_returns_confirmation(self, mock_dup, mock_inject):
        mock_dup.return_value = {"is_duplicate": False, "matches": []}
        mock_inject.return_value = {
            "entry_id": "pneuma-abc123",
            "collection": "chat-knowledge-solutions",
            "ingested_at": 1000.0,
        }
        from mcp_server.tools.memory_tools import save_knowledge

        result = _run(save_knowledge("Fix: restart the service", tags="ops,fix"))
        assert "pneuma-abc123" in result
        assert "Saved to" in result
        # Verify inject_entry was called with correct args
        call_kwargs = mock_inject.call_args
        assert call_kwargs[1]["content"] == "Fix: restart the service"
        assert call_kwargs[1]["metadata"]["tags"] == "ops,fix"


# ── palace_overview (replaces list_topics, palace_status, palace_taxonomy) ────

class TestPalaceOverview:
    @patch("mcp_server.tools.memory_tools._status")
    def test_summary_returns_status(self, mock_status):
        mock_status.return_value = {
            "total_drawers": 150,
            "wings": {"code": 80, "decisions": 70},
            "rooms": {"api": 40, "architecture": 30},
            "palace_path": "/home/test/.mempalace/palace",
        }
        from mcp_server.tools.memory_tools import palace_overview

        result = _run(palace_overview())
        assert "150" in result
        assert "2" in result  # 2 wings

    @patch("mcp_server.tools.memory_tools._taxonomy")
    @patch("mcp_server.tools.memory_tools._status")
    def test_full_includes_taxonomy(self, mock_status, mock_tax):
        mock_status.return_value = {
            "total_drawers": 150,
            "wings": {"code": 80, "decisions": 70},
            "rooms": {"api": 40, "architecture": 30},
            "palace_path": "/home/test/.mempalace/palace",
        }
        mock_tax.return_value = {"code": {"api": 40, "config": 10}, "decisions": {"architecture": 30}}
        from mcp_server.tools.memory_tools import palace_overview

        result = _run(palace_overview(detail="full"))
        assert "code" in result
        assert "api" in result
        assert "architecture" in result


# ── delete_entry (was delete_knowledge) ──────────────────────────

class TestDeleteEntry:
    @patch("mcp_server.tools.memory_tools._delete")
    def test_successful_delete(self, mock_del):
        mock_del.return_value = {"success": True, "drawer_id": "abc123"}
        from mcp_server.tools.memory_tools import delete_entry

        result = _run(delete_entry("abc123"))
        assert "Deleted" in result
        assert "abc123" in result

    @patch("mcp_server.tools.memory_tools._delete")
    def test_failed_delete(self, mock_del):
        mock_del.return_value = {"success": False, "error": "Entry not found"}
        from mcp_server.tools.memory_tools import delete_entry

        result = _run(delete_entry("missing"))
        assert "Failed" in result


# ── optimize_memory ──────────────────────────────────────────────

class TestOptimizeMemory:
    @patch("mcp_server.tools.memory_tools.run_optimize")
    def test_returns_report(self, mock_optimize):
        from core.auto_org.refactor import OptimizeReport

        mock_optimize.return_value = OptimizeReport(
            duplicates_merged=3,
            stale_removed=1,
            collections_scanned=5,
            errors=[],
        )
        from mcp_server.tools.memory_tools import optimize_memory

        result = _run(optimize_memory())
        assert "3" in result
        assert "1" in result
        assert "5" in result


# ── knowledge_stats → now folded into palace_overview(detail="full") ────────

class TestKgStatsViaPalaceOverview:
    @patch("core.palace.kg_stats")
    @patch("mcp_server.tools.memory_tools._taxonomy")
    @patch("mcp_server.tools.memory_tools._status")
    def test_full_detail_includes_kg_stats(self, mock_status, mock_tax, mock_kg):
        mock_status.return_value = {
            "total_drawers": 100, "wings": {"a": 1}, "rooms": {"b": 1},
            "palace_path": "/tmp/palace",
        }
        mock_tax.return_value = {"a": {"b": 100}}
        mock_kg.return_value = {
            "entities": 25,
            "triples": 60,
            "current_facts": 50,
            "expired_facts": 10,
            "relationship_types": ["uses", "depends_on"],
        }
        from mcp_server.tools.memory_tools import palace_overview

        result = _run(palace_overview(detail="full"))
        assert "Knowledge graph" in result
        assert "25" in result
        assert "60" in result
        assert "uses" in result


# ── track_fact ───────────────────────────────────────────────────

class TestTrackFact:
    @patch("mcp_server.tools.kg_tools.get_kg")
    def test_records_fact(self, mock_get_kg):
        kg = MagicMock()
        kg.add_triple.return_value = "triple-001"
        mock_get_kg.return_value = kg
        from mcp_server.tools.kg_tools import track_fact

        result = _run(track_fact("Auth Service", "uses", "JWT"))
        assert "triple-001" in result
        assert "Auth Service" in result
        assert "uses" in result
        assert "JWT" in result
        kg.add_triple.assert_called_once_with(
            subject="Auth Service",
            predicate="uses",
            obj="JWT",
            valid_from=None,
            confidence=1.0,
        )

    @patch("mcp_server.tools.kg_tools.get_kg")
    def test_with_valid_from_and_confidence(self, mock_get_kg):
        kg = MagicMock()
        kg.add_triple.return_value = "triple-002"
        mock_get_kg.return_value = kg
        from mcp_server.tools.kg_tools import track_fact

        result = _run(track_fact("DB", "migrated_to", "PostgreSQL",
                                 valid_from="2026-01-15", confidence=0.9))
        kg.add_triple.assert_called_once_with(
            subject="DB",
            predicate="migrated_to",
            obj="PostgreSQL",
            valid_from="2026-01-15",
            confidence=0.9,
        )
        assert "triple-002" in result


# ── query_facts ──────────────────────────────────────────────────

class TestQueryFacts:
    @patch("mcp_server.tools.kg_tools.get_kg")
    def test_returns_facts(self, mock_get_kg):
        kg = MagicMock()
        kg.query_entity.return_value = [
            {
                "subject": "Auth",
                "predicate": "uses",
                "object": "JWT",
                "direction": "outgoing",
                "current": True,
                "valid_from": "2026-01-01",
            }
        ]
        mock_get_kg.return_value = kg
        from mcp_server.tools.kg_tools import query_facts

        result = _run(query_facts("Auth"))
        assert "Auth" in result
        assert "uses" in result
        assert "JWT" in result
        kg.query_entity.assert_called_once_with(
            name="Auth", as_of=None, direction="both"
        )

    @patch("mcp_server.tools.kg_tools.get_kg")
    def test_no_facts(self, mock_get_kg):
        kg = MagicMock()
        kg.query_entity.return_value = []
        mock_get_kg.return_value = kg
        from mcp_server.tools.kg_tools import query_facts

        result = _run(query_facts("Unknown"))
        assert "No facts" in result

    @patch("mcp_server.tools.kg_tools.get_kg")
    def test_chronological_mode(self, mock_get_kg):
        kg = MagicMock()
        kg.timeline.return_value = [
            {
                "subject": "DB",
                "predicate": "uses",
                "object": "MySQL",
                "current": False,
                "valid_from": "2024-01-01",
                "valid_to": "2025-06-01",
            },
            {
                "subject": "DB",
                "predicate": "uses",
                "object": "PostgreSQL",
                "current": True,
                "valid_from": "2025-06-01",
            },
        ]
        mock_get_kg.return_value = kg
        from mcp_server.tools.kg_tools import query_facts

        result = _run(query_facts("DB", chronological=True))
        assert "Timeline" in result
        assert "MySQL" in result
        assert "PostgreSQL" in result
        assert "expired" in result
        assert "current" in result


# ── invalidate_fact ──────────────────────────────────────────────

class TestInvalidateFact:
    @patch("mcp_server.tools.kg_tools.get_kg")
    def test_invalidates_fact(self, mock_get_kg):
        kg = MagicMock()
        mock_get_kg.return_value = kg
        from mcp_server.tools.kg_tools import invalidate_fact

        result = _run(invalidate_fact("Auth", "uses", "JWT", ended="2026-03-01"))
        assert "Invalidated" in result
        assert "Auth" in result
        kg.invalidate.assert_called_once_with(
            subject="Auth", predicate="uses", obj="JWT", ended="2026-03-01"
        )

    @patch("mcp_server.tools.kg_tools.get_kg")
    def test_invalidate_without_ended(self, mock_get_kg):
        kg = MagicMock()
        mock_get_kg.return_value = kg
        from mcp_server.tools.kg_tools import invalidate_fact

        result = _run(invalidate_fact("DB", "uses", "MySQL"))
        assert "today" in result
        kg.invalidate.assert_called_once_with(
            subject="DB", predicate="uses", obj="MySQL", ended=None
        )


# ── explore_palace ───────────────────────────────────────────────

class TestExplorePalace:
    @patch("mcp_server.tools.nav_tools.traverse_palace")
    def test_returns_graph(self, mock_traverse):
        mock_traverse.return_value = [
            {"hop": 0, "room": "api", "wings": ["code"], "count": 40},
            {"hop": 1, "room": "auth", "wings": ["code", "decisions"], "count": 25},
        ]
        from mcp_server.tools.nav_tools import explore_palace

        result = _run(explore_palace("api"))
        assert "api" in result
        assert "auth" in result
        assert "hop 0" in result
        assert "hop 1" in result
        mock_traverse.assert_called_once_with("api", max_hops=2)

    @patch("mcp_server.tools.nav_tools.traverse_palace")
    def test_no_connections(self, mock_traverse):
        mock_traverse.return_value = []
        from mcp_server.tools.nav_tools import explore_palace

        result = _run(explore_palace("isolated"))
        assert "No connections" in result

    @patch("mcp_server.tools.nav_tools.traverse_palace")
    def test_max_hops_capped(self, mock_traverse):
        mock_traverse.return_value = []
        from mcp_server.tools.nav_tools import explore_palace

        _run(explore_palace("api", max_hops=10))
        mock_traverse.assert_called_once_with("api", max_hops=5)


# ── find_bridges ─────────────────────────────────────────────────

class TestFindBridges:
    @patch("mcp_server.tools.nav_tools.find_palace_tunnels")
    def test_returns_tunnels(self, mock_tunnels):
        mock_tunnels.return_value = [
            {"room": "auth", "wings": ["code", "decisions"], "count": 15},
        ]
        from mcp_server.tools.nav_tools import find_bridges

        result = _run(find_bridges(wing_a="code", wing_b="decisions"))
        assert "auth" in result
        assert "code" in result
        assert "decisions" in result
        mock_tunnels.assert_called_once_with(wing_a="code", wing_b="decisions")

    @patch("mcp_server.tools.nav_tools.find_palace_tunnels")
    def test_no_bridges(self, mock_tunnels):
        mock_tunnels.return_value = []
        from mcp_server.tools.nav_tools import find_bridges

        result = _run(find_bridges(wing_a="code", wing_b="docs"))
        assert "No cross-wing connections" in result

    @patch("mcp_server.tools.nav_tools.find_palace_tunnels")
    def test_no_filters(self, mock_tunnels):
        mock_tunnels.return_value = []
        from mcp_server.tools.nav_tools import find_bridges

        _run(find_bridges())
        mock_tunnels.assert_called_once_with(wing_a=None, wing_b=None)


# ── write_diary ──────────────────────────────────────────────────

class TestWriteDiary:
    @patch("mcp_server.tools.diary_tools._write")
    def test_successful_write(self, mock_write):
        mock_write.return_value = {
            "success": True,
            "entry_id": "diary-001",
            "timestamp": "2026-01-15T10:30:00",
        }
        from mcp_server.tools.diary_tools import write_diary

        result = _run(write_diary("Migrated auth to JWT", topic="architecture"))
        assert "diary-001" in result
        assert "architecture" in result
        mock_write.assert_called_once_with(
            agent_name="copilot",
            entry="Migrated auth to JWT",
            topic="architecture",
        )

    @patch("mcp_server.tools.diary_tools._write")
    def test_failed_write(self, mock_write):
        mock_write.return_value = {"success": False, "error": "disk full"}
        from mcp_server.tools.diary_tools import write_diary

        result = _run(write_diary("test"))
        assert "Failed" in result
        assert "disk full" in result


# ── read_diary ───────────────────────────────────────────────────

class TestReadDiary:
    @patch("mcp_server.tools.diary_tools._read")
    def test_returns_entries(self, mock_read):
        mock_read.return_value = {
            "entries": [
                {"date": "2026-01-15", "topic": "debugging", "content": "Fixed auth bug"},
                {"date": "2026-01-14", "topic": "general", "content": "Setup project"},
            ],
            "total": 5,
            "showing": 2,
        }
        from mcp_server.tools.diary_tools import read_diary

        result = _run(read_diary(limit=2))
        assert "Fixed auth bug" in result
        assert "Setup project" in result
        assert "showing 2 of 5" in result
        mock_read.assert_called_once_with(agent_name="copilot", last_n=2)

    @patch("mcp_server.tools.diary_tools._read")
    def test_no_entries(self, mock_read):
        mock_read.return_value = {"entries": []}
        from mcp_server.tools.diary_tools import read_diary

        result = _run(read_diary())
        assert "No diary entries" in result


# ── import_content ───────────────────────────────────────────────

class TestImportContent:
    @patch("mcp_server.tools.import_tools.import_file")
    def test_import_file(self, mock_import_file):
        mock_import_file.return_value = {
            "doc_type": "markdown",
            "entries_stored": 12,
        }
        from mcp_server.tools.import_tools import import_content

        result = _run(import_content(file_path="/tmp/doc.md"))
        assert "12" in result
        assert "markdown" in result
        mock_import_file.assert_called_once_with(
            path="/tmp/doc.md", doc_type="auto", wing="", room=""
        )

    @patch("mcp_server.tools.import_tools._import_content")
    def test_import_pasted_text(self, mock_import):
        mock_import.return_value = {
            "doc_type": "general",
            "entries_stored": 3,
        }
        from mcp_server.tools.import_tools import import_content

        result = _run(import_content(content="Some pasted text here"))
        assert "3" in result
        mock_import.assert_called_once_with(
            content="Some pasted text here",
            doc_type="auto",
            title="",
            wing="",
            room="",
        )

    def test_import_nothing(self):
        from mcp_server.tools.import_tools import import_content

        result = _run(import_content())
        assert "Nothing to import" in result

    @patch("mcp_server.tools.import_tools.import_file")
    def test_file_not_found(self, mock_import_file):
        mock_import_file.side_effect = FileNotFoundError()
        from mcp_server.tools.import_tools import import_content

        result = _run(import_content(file_path="/tmp/missing.md"))
        assert "File not found" in result


# ── check_recent_chat ────────────────────────────────────────────

class TestCheckRecentChat:
    @patch("mcp_server.tools.chat_tools.urllib.request.urlopen")
    @patch("mcp_server.tools.chat_tools.SLACK_USER_TOKEN", "xoxp-test")
    def test_returns_messages(self, mock_urlopen):
        import io
        import json

        response_data = json.dumps({
            "ok": True,
            "messages": {
                "matches": [
                    {
                        "username": "alice",
                        "text": "We should use Redis for caching",
                        "channel": {"name": "engineering"},
                    }
                ]
            },
        }).encode()
        mock_urlopen.return_value.__enter__ = lambda s: MagicMock(read=lambda: response_data)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        from mcp_server.tools.chat_tools import check_recent_chat

        result = _run(check_recent_chat("caching"))
        assert "Redis" in result
        assert "alice" in result

    @patch("mcp_server.tools.chat_tools.SLACK_BOT_TOKEN", "")
    @patch("mcp_server.tools.chat_tools.SLACK_USER_TOKEN", "")
    def test_no_token(self):
        from mcp_server.tools.chat_tools import check_recent_chat

        result = _run(check_recent_chat("anything"))
        assert "not configured" in result

    @patch("mcp_server.tools.chat_tools.urllib.request.urlopen")
    @patch("mcp_server.tools.chat_tools.SLACK_USER_TOKEN", "xoxp-test")
    def test_no_matches(self, mock_urlopen):
        import json

        response_data = json.dumps({
            "ok": True,
            "messages": {"matches": []},
        }).encode()
        mock_urlopen.return_value.__enter__ = lambda s: MagicMock(read=lambda: response_data)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        from mcp_server.tools.chat_tools import check_recent_chat

        result = _run(check_recent_chat("nonexistent"))
        assert "No recent Slack messages" in result


# ── ask_team ─────────────────────────────────────────────────────

class TestAskTeam:
    @patch("mcp_server.tools.chat_tools.urllib.request.urlopen")
    @patch("mcp_server.tools.chat_tools.SLACK_DEFAULT_CHANNEL", "C123")
    @patch("mcp_server.tools.chat_tools.SLACK_BOT_TOKEN", "xoxb-test")
    def test_posts_question(self, mock_urlopen):
        import json

        response_data = json.dumps({"ok": True}).encode()
        mock_urlopen.return_value.__enter__ = lambda s: MagicMock(read=lambda: response_data)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        from mcp_server.tools.chat_tools import ask_team

        result = _run(ask_team("How do we handle auth?"))
        assert "posted" in result.lower() or "Question posted" in result

    @patch("mcp_server.tools.chat_tools.SLACK_BOT_TOKEN", "")
    def test_no_token(self):
        from mcp_server.tools.chat_tools import ask_team

        result = _run(ask_team("anything"))
        assert "not configured" in result

    @patch("mcp_server.tools.chat_tools.SLACK_DEFAULT_CHANNEL", "")
    @patch("mcp_server.tools.chat_tools.SLACK_BOT_TOKEN", "xoxb-test")
    def test_no_channel(self):
        from mcp_server.tools.chat_tools import ask_team

        result = _run(ask_team("question"))
        assert "No channel" in result


# ── ingest_slack_channel ─────────────────────────────────────────

class TestIngestSlackChannel:
    @patch("mcp_server.tools.slack_ingest_tools.SLACK_BOT_TOKEN", "")
    def test_no_token(self):
        from mcp_server.tools.slack_ingest_tools import ingest_slack_channel

        result = _run(ingest_slack_channel("C123"))
        assert "not configured" in result

    @patch("mcp_server.tools.slack_ingest_tools._ALLOWED_CHANNELS", set())
    @patch("mcp_server.tools.slack_ingest_tools._fetch_history")
    @patch("mcp_server.tools.slack_ingest_tools.SLACK_BOT_TOKEN", "xoxb-test")
    def test_no_messages(self, mock_fetch):
        mock_fetch.return_value = []
        from mcp_server.tools.slack_ingest_tools import ingest_slack_channel

        result = _run(ingest_slack_channel("C123"))
        assert "No messages" in result

    @patch("mcp_server.tools.slack_ingest_tools._ALLOWED_CHANNELS", set())
    @patch("mcp_server.tools.slack_ingest_tools._fetch_history")
    @patch("mcp_server.tools.slack_ingest_tools.SLACK_BOT_TOKEN", "xoxb-test")
    def test_fetch_error(self, mock_fetch):
        mock_fetch.return_value = "Slack API error: channel_not_found"
        from mcp_server.tools.slack_ingest_tools import ingest_slack_channel

        result = _run(ingest_slack_channel("C_INVALID"))
        assert "channel_not_found" in result


# ── escalate_to_human ────────────────────────────────────────────

class TestEscalateToHuman:
    @patch("mcp_server.tools.escalation.urllib.request.urlopen")
    @patch("mcp_server.tools.escalation.ESCALATION_CHANNEL", "C999")
    @patch("mcp_server.tools.escalation.SLACK_BOT_TOKEN", "xoxb-test")
    def test_successful_escalation(self, mock_urlopen):
        import json

        response_data = json.dumps({"ok": True}).encode()
        mock_urlopen.return_value.__enter__ = lambda s: MagicMock(read=lambda: response_data)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        from mcp_server.tools.escalation import escalate_to_human

        result = _run(escalate_to_human("def foo(): pass", "What does foo do?"))
        assert "successfully" in result.lower() or "sent" in result.lower()

    @patch("mcp_server.tools.escalation.SLACK_BOT_TOKEN", "")
    def test_not_configured(self):
        from mcp_server.tools.escalation import escalate_to_human

        result = _run(escalate_to_human("code", "question"))
        assert "not configured" in result

    @patch("mcp_server.tools.escalation.urllib.request.urlopen")
    @patch("mcp_server.tools.escalation.ESCALATION_CHANNEL", "C999")
    @patch("mcp_server.tools.escalation.SLACK_BOT_TOKEN", "xoxb-test")
    def test_api_failure(self, mock_urlopen):
        import json

        response_data = json.dumps({"ok": False, "error": "invalid_auth"}).encode()
        mock_urlopen.return_value.__enter__ = lambda s: MagicMock(read=lambda: response_data)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        from mcp_server.tools.escalation import escalate_to_human

        result = _run(escalate_to_human("code", "question"))
        assert "failed" in result.lower() or "invalid_auth" in result
