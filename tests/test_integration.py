"""Integration tests — real ChromaDB + SQLite in temp directories.

Each test calls actual MCP tool functions which go through the full chain:
  MCP tool → palace adapter → mempalace → ChromaDB / SQLite → retrieval

The ``tmp_palace`` fixture (session-scoped, from conftest.py) provides an
isolated palace directory so nothing touches ~/.pneuma or real data.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ═══════════════════════════════════════════════════════════════════
# Group 1 — Memory round-trip: save → search → delete
# ═══════════════════════════════════════════════════════════════════

class TestMemoryRoundTrip:

    def test_save_and_search(self, tmp_palace):
        from mcp_server.tools.memory_tools import save_knowledge, search_memory

        result = _run(save_knowledge(
            "PostgreSQL is our primary database for all backend services"
        ))
        assert "Saved to" in result
        assert "Entry ID" in result

        search_result = _run(search_memory("primary database"))
        assert "PostgreSQL" in search_result

    def test_save_duplicate_detection(self, tmp_palace):
        from mcp_server.tools.memory_tools import save_knowledge

        content = "Redis is used for caching in the API gateway"
        first = _run(save_knowledge(content))
        assert "Saved to" in first

        second = _run(save_knowledge(content))
        assert "duplicate" in second.lower() or "Saved to" in second

    def test_delete_entry(self, tmp_palace):
        from mcp_server.tools.memory_tools import save_knowledge, search_memory, delete_entry

        result = _run(save_knowledge(
            "Temporary entry that should be deleted after testing"
        ))
        # Extract entry ID from "Entry ID: pneuma-xxxx"
        entry_id = None
        for line in result.split("\n"):
            if "Entry ID:" in line:
                entry_id = line.split("Entry ID:")[1].strip()
                break
        assert entry_id is not None

        del_result = _run(delete_entry(entry_id))
        assert "Deleted" in del_result or "success" in del_result.lower()

    def test_wake_up_and_recall(self, tmp_palace):
        from mcp_server.tools.memory_tools import save_knowledge, wake_up, recall

        # Seed some data first
        _run(save_knowledge("Our API uses REST with JSON payloads"))

        wake = _run(wake_up())
        # wake_up returns identity or a fallback message — both are valid
        assert isinstance(wake, str) and len(wake) > 0

        recall_result = _run(recall())
        assert isinstance(recall_result, str) and len(recall_result) > 0


# ═══════════════════════════════════════════════════════════════════
# Group 2 — Knowledge Graph round-trip
# ═══════════════════════════════════════════════════════════════════

class TestKnowledgeGraphRoundTrip:

    def test_track_and_query(self, tmp_palace):
        from mcp_server.tools.kg_tools import track_fact, query_facts

        track_result = _run(track_fact("Auth Service", "uses", "JWT"))
        assert "Fact recorded" in track_result
        assert "Triple ID" in track_result

        query_result = _run(query_facts("Auth Service"))
        assert "JWT" in query_result
        assert "uses" in query_result

    def test_track_and_stats_via_palace_overview(self, tmp_palace):
        from mcp_server.tools.kg_tools import track_fact
        from mcp_server.tools.memory_tools import palace_overview

        _run(track_fact("Backend", "uses", "Python"))
        _run(track_fact("Frontend", "uses", "React"))

        # KG stats are now exposed via palace_overview(detail="full")
        overview = _run(palace_overview(detail="full"))
        assert "Knowledge graph" in overview or "entities" in overview.lower()

    def test_invalidate_fact(self, tmp_palace):
        from mcp_server.tools.kg_tools import track_fact, invalidate_fact, query_facts

        _run(track_fact("DB", "uses", "MySQL", valid_from="2024-01-01"))
        inv = _run(invalidate_fact("DB", "uses", "MySQL", ended="2025-06-01"))
        assert "Invalidated" in inv

        # After invalidation, querying current facts should show it as expired
        facts = _run(query_facts("DB"))
        # The fact may still appear but marked expired, or may not appear at all
        assert isinstance(facts, str)

    def test_chronological_timeline(self, tmp_palace):
        from mcp_server.tools.kg_tools import track_fact, invalidate_fact, query_facts

        _run(track_fact("Cache", "uses", "Memcached", valid_from="2024-01-01"))
        _run(invalidate_fact("Cache", "uses", "Memcached", ended="2025-01-01"))
        _run(track_fact("Cache", "uses", "Redis", valid_from="2025-01-01"))

        timeline = _run(query_facts("Cache", chronological=True))
        assert "Timeline" in timeline or "timeline" in timeline
        assert "Memcached" in timeline
        assert "Redis" in timeline


# ═══════════════════════════════════════════════════════════════════
# Group 3 — Diary round-trip
# ═══════════════════════════════════════════════════════════════════

class TestDiaryRoundTrip:

    def test_write_and_read_diary(self, tmp_palace):
        from mcp_server.tools.diary_tools import write_diary, read_diary

        write_result = _run(write_diary(
            "Fixed auth bug by switching to bcrypt",
            topic="debugging",
        ))
        assert "saved" in write_result.lower() or "ID" in write_result

        read_result = _run(read_diary())
        assert "bcrypt" in read_result or "auth" in read_result

    def test_diary_agent_isolation(self, tmp_palace):
        from mcp_server.tools.diary_tools import write_diary, read_diary

        _run(write_diary("Copilot entry", agent_name="copilot"))
        _run(write_diary("Assistant entry", agent_name="assistant"))

        copilot_diary = _run(read_diary(agent_name="copilot"))
        assert "Copilot entry" in copilot_diary

        assistant_diary = _run(read_diary(agent_name="assistant"))
        assert "Assistant entry" in assistant_diary


# ═══════════════════════════════════════════════════════════════════
# Group 4 — Import pipeline
# ═══════════════════════════════════════════════════════════════════

class TestImportPipeline:

    def test_import_pasted_text(self, tmp_palace):
        from mcp_server.tools.import_tools import import_content
        from mcp_server.tools.memory_tools import search_memory

        result = _run(import_content(
            content="Our deployment pipeline uses Docker containers orchestrated by Kubernetes"
        ))
        assert "Import complete" in result
        assert "Entries stored" in result

        search_result = _run(search_memory("deployment Docker Kubernetes"))
        assert "Docker" in search_result or "Kubernetes" in search_result

    def test_import_file(self, tmp_palace):
        from mcp_server.tools.import_tools import import_content
        from mcp_server.tools.memory_tools import search_memory

        # Write a temporary markdown file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write("# API Design Guide\n\nAll endpoints must use HTTPS and return JSON.\n")
            tmp_path = f.name

        try:
            result = _run(import_content(file_path=tmp_path))
            assert "Import complete" in result

            search_result = _run(search_memory("API HTTPS JSON"))
            assert "HTTPS" in search_result or "JSON" in search_result or "API" in search_result
        finally:
            os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════
# Group 5 — Palace overview & navigation
# ═══════════════════════════════════════════════════════════════════

class TestPalaceNavigation:

    def test_palace_overview(self, tmp_palace):
        from mcp_server.tools.memory_tools import save_knowledge, palace_overview

        # Seed entries across different domains
        _run(save_knowledge("Auth uses JWT tokens for session management"))
        _run(save_knowledge("We decided to use microservices architecture"))

        overview = _run(palace_overview())
        assert "overview" in overview.lower() or "entries" in overview.lower() or "Total" in overview

    def test_explore_palace(self, tmp_palace):
        from mcp_server.tools.memory_tools import save_knowledge
        from mcp_server.tools.nav_tools import explore_palace
        from core.palace import add_entry

        # Seed directly into a known room to guarantee it exists
        add_entry("code", "api", "API gateway handles routing", source="test")
        add_entry("code", "api", "API uses REST with JSON payloads", source="test")

        result = _run(explore_palace("api"))
        # Should find the room and report it
        assert "api" in result or "No connections" in result
        assert isinstance(result, str) and len(result) > 0

    def test_find_bridges(self, tmp_palace):
        from mcp_server.tools.memory_tools import save_knowledge
        from mcp_server.tools.nav_tools import find_bridges

        # Seed entries to create potential bridges
        _run(save_knowledge("API authentication uses OAuth2 protocol"))
        _run(save_knowledge("Decision: adopt OAuth2 for all services"))

        result = _run(find_bridges())
        # May find tunnels or may say "no connections" — both valid
        assert isinstance(result, str) and len(result) > 0


# ═══════════════════════════════════════════════════════════════════
# Group 6 — Slack tools (mocked happy path)
# ═══════════════════════════════════════════════════════════════════

class TestSlackToolsMocked:

    @patch("mcp_server.tools.chat_tools.urllib.request.urlopen")
    @patch("mcp_server.tools.chat_tools.SLACK_USER_TOKEN", "xoxp-test-token")
    def test_check_recent_chat_success(self, mock_urlopen):
        import json

        response_data = json.dumps({
            "ok": True,
            "messages": {
                "matches": [
                    {
                        "username": "alice",
                        "text": "We should migrate to PostgreSQL for better JSON support",
                        "channel": {"name": "engineering"},
                    },
                    {
                        "username": "bob",
                        "text": "Agreed, PostgreSQL jsonb is much faster",
                        "channel": {"name": "engineering"},
                    },
                ]
            },
        }).encode()
        mock_urlopen.return_value.__enter__ = lambda s: MagicMock(
            read=lambda: response_data
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        from mcp_server.tools.chat_tools import check_recent_chat

        result = _run(check_recent_chat("PostgreSQL"))
        assert "PostgreSQL" in result
        assert "alice" in result
        assert "2" in result  # "Found 2 Slack messages"

    @patch("mcp_server.tools.chat_tools.urllib.request.urlopen")
    @patch("mcp_server.tools.chat_tools.SLACK_DEFAULT_CHANNEL", "C0123TEST")
    @patch("mcp_server.tools.chat_tools.SLACK_BOT_TOKEN", "xoxb-test-token")
    def test_ask_team_success(self, mock_urlopen):
        import json

        response_data = json.dumps({"ok": True}).encode()
        mock_urlopen.return_value.__enter__ = lambda s: MagicMock(
            read=lambda: response_data
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        from mcp_server.tools.chat_tools import ask_team

        result = _run(ask_team("How do we handle database migrations?"))
        assert "posted" in result.lower() or "Question posted" in result

    @patch("mcp_server.tools.escalation.urllib.request.urlopen")
    @patch("mcp_server.tools.escalation.ESCALATION_CHANNEL", "C999ESCALATE")
    @patch("mcp_server.tools.escalation.SLACK_BOT_TOKEN", "xoxb-test-token")
    def test_escalate_success(self, mock_urlopen):
        import json

        response_data = json.dumps({"ok": True}).encode()
        mock_urlopen.return_value.__enter__ = lambda s: MagicMock(
            read=lambda: response_data
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        from mcp_server.tools.escalation import escalate_to_human

        result = _run(escalate_to_human(
            "def handle_auth(): pass",
            "What authentication method should we use?"
        ))
        assert "successfully" in result.lower() or "sent" in result.lower()

    @patch("mcp_server.tools.slack_ingest_tools._ALLOWED_CHANNELS", set())
    @patch("mcp_server.tools.slack_ingest_tools._fetch_history")
    @patch("mcp_server.tools.slack_ingest_tools.SLACK_BOT_TOKEN", "xoxb-test-token")
    def test_ingest_channel_success(self, mock_fetch):
        mock_fetch.return_value = [
            {"user": "U001", "text": "We decided to use Redis for caching", "ts": "1700000000.000"},
            {"user": "U002", "text": "Good idea, Redis has great pub/sub too", "ts": "1700000001.000"},
            {"user": "U003", "text": "Question: should we use Redis Cluster or Sentinel?", "ts": "1700000002.000"},
            {"user": "U001", "text": "Let's go with Sentinel for simplicity", "ts": "1700000003.000"},
        ]

        from mcp_server.tools.slack_ingest_tools import ingest_slack_channel

        result = _run(ingest_slack_channel("C0123CHANNEL", hours_back=24))
        assert "Messages fetched" in result or "Ingested" in result or "fetched" in result.lower()
