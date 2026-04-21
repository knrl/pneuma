"""
End-to-end test — exercises all 20 MCP tools against the real openpilot palace
with meaningful project data and measures wall-clock time for each operation.

Run:  python -m pytest tests/test_e2e_openpilot.py -v -s
  (-s shows timing output)

Requires:
  pneuma init ~/Documents/workspace/openpilot   (one-time setup)
"""

import asyncio
import os
import time
from unittest.mock import patch, MagicMock

import pytest

from core.palace import configure

# ── Openpilot project root ───────────────────────────────────────
OPENPILOT_ROOT = os.environ.get(
    "OPENPILOT_ROOT", "/home/knrl/Documents/workspace/openpilot"
)

if not os.path.exists(OPENPILOT_ROOT):
    pytest.skip(
        f"openpilot not found at {OPENPILOT_ROOT} — "
        "set OPENPILOT_ROOT env var or run `pneuma init <path>` first",
        allow_module_level=True,
    )


# ── Helpers ──────────────────────────────────────────────────────

def _run(coro):
    """Run an async function synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


def timed(label, coro):
    """Run *coro*, print elapsed time, assert < 30 s."""
    t0 = time.perf_counter()
    result = _run(coro)
    elapsed = time.perf_counter() - t0
    tag = "OK" if elapsed < 10 else "SLOW" if elapsed < 30 else "TOO SLOW"
    print(f"  [{tag}] {label}: {elapsed:.2f}s")
    assert elapsed < 30, f"{label} took {elapsed:.1f}s (max 30s)"
    return result


# ── Session fixture — activate real openpilot palace ─────────────

@pytest.fixture(scope="session", autouse=True)
def openpilot_palace():
    """Point the palace singletons at the real openpilot project."""
    configure(OPENPILOT_ROOT)
    yield OPENPILOT_ROOT


# ═════════════════════════════════════════════════════════════════
# Phase 1 — Import real openpilot docs
# ═════════════════════════════════════════════════════════════════

class TestPhase1Import:

    def test_01_import_readme(self):
        from mcp_server.tools.import_tools import import_content

        result = timed("import README.md", import_content(
            file_path=f"{OPENPILOT_ROOT}/README.md",
        ))
        assert "Import complete" in result or "entries" in result.lower()

    def test_02_import_safety(self):
        from mcp_server.tools.import_tools import import_content

        result = timed("import SAFETY.md", import_content(
            file_path=f"{OPENPILOT_ROOT}/docs/SAFETY.md",
        ))
        assert "Import complete" in result or "entries" in result.lower()

    def test_03_import_contributing(self):
        from mcp_server.tools.import_tools import import_content

        result = timed("import CONTRIBUTING.md", import_content(
            file_path=f"{OPENPILOT_ROOT}/docs/CONTRIBUTING.md",
        ))
        assert "Import complete" in result or "entries" in result.lower()

    def test_04_import_limitations(self):
        from mcp_server.tools.import_tools import import_content

        result = timed("import LIMITATIONS.md", import_content(
            file_path=f"{OPENPILOT_ROOT}/docs/LIMITATIONS.md",
        ))
        assert "Import complete" in result or "entries" in result.lower()

    def test_05_import_pasted_text(self):
        from mcp_server.tools.import_tools import import_content

        result = timed("import pasted text", import_content(
            content=(
                "openpilot uses a panda microcontroller for vehicle CAN bus "
                "communication. The panda enforces safety limits at hardware "
                "level — it constrains steering torque and braking force to "
                "prevent dangerous actuations. All safety-critical code follows "
                "MISRA C:2012 guidelines. The system uses cereal for IPC "
                "messaging between processes, with all messages defined in "
                "capnp schemas."
            ),
            title="openpilot architecture overview",
        ))
        assert "Import complete" in result or "entries" in result.lower()


# ═════════════════════════════════════════════════════════════════
# Phase 2 — Memory tools (7 tools, 10 tests)
# ═════════════════════════════════════════════════════════════════

class TestPhase2Memory:

    def test_01_wake_up(self):
        from mcp_server.tools.memory_tools import wake_up

        result = timed("wake_up", wake_up())
        assert isinstance(result, str) and len(result) > 0

    def test_02_recall(self):
        from mcp_server.tools.memory_tools import recall

        result = timed("recall", recall())
        assert isinstance(result, str) and len(result) > 0

    def test_03_search_safety(self):
        from mcp_server.tools.memory_tools import search_memory

        result = timed("search 'safety steering torque'", search_memory(
            "safety steering torque limits",
        ))
        assert any(w in result.lower() for w in [
            "safety", "steering", "torque", "driver",
        ]), f"Expected safety content, got: {result[:300]}"

    def test_04_search_contributing(self):
        from mcp_server.tools.memory_tools import search_memory

        result = timed("search 'contribute pull request'", search_memory(
            "how to contribute pull request",
        ))
        assert any(w in result.lower() for w in [
            "pull", "contribut", "pr", "merge",
        ]), f"Expected contributing content, got: {result[:300]}"

    def test_05_search_grouped(self):
        from mcp_server.tools.memory_tools import search_memory

        result = timed("search grouped", search_memory(
            "openpilot features", group_by_location=True,
        ))
        assert isinstance(result, str) and len(result) > 0

    def test_06_save_knowledge(self):
        from mcp_server.tools.memory_tools import save_knowledge

        result = timed("save_knowledge", save_knowledge(
            "Decision: We chose cereal + capnp for IPC because it provides "
            "zero-copy deserialization and strong schema evolution guarantees, "
            "which are critical for real-time automotive systems at 100 Hz.",
        ))
        assert "Saved to" in result or "duplicate" in result.lower()

    def test_07_palace_overview_summary(self):
        from mcp_server.tools.memory_tools import palace_overview

        result = timed("palace_overview (summary)", palace_overview())
        assert isinstance(result, str) and len(result) > 0

    def test_08_palace_overview_full(self):
        from mcp_server.tools.memory_tools import palace_overview

        result = timed("palace_overview (full)", palace_overview(detail="full"))
        assert isinstance(result, str) and len(result) > 0

    def test_09_save_and_delete(self):
        from mcp_server.tools.memory_tools import save_knowledge, delete_entry

        save_result = timed("save (temp entry)", save_knowledge(
            "Temporary test entry for deletion — ignore this content",
        ))
        entry_id = None
        for line in save_result.splitlines():
            if "Entry ID:" in line:
                entry_id = line.split("Entry ID:")[1].strip()
        if entry_id:
            del_result = timed("delete_entry", delete_entry(entry_id))
            assert "Deleted" in del_result or "success" in del_result.lower()
        else:
            pytest.skip("Could not extract entry ID from save result")

    def test_10_optimize_memory(self):
        from mcp_server.tools.memory_tools import optimize_memory

        result = timed("optimize_memory", optimize_memory())
        assert isinstance(result, str) and len(result) > 0


# ═════════════════════════════════════════════════════════════════
# Phase 3 — Knowledge Graph (4 tools, 5 tests)
# ═════════════════════════════════════════════════════════════════

class TestPhase3KnowledgeGraph:

    def test_01_track_facts(self):
        from mcp_server.tools.kg_tools import track_fact

        facts = [
            ("openpilot", "uses", "panda", "2017-01-01"),
            ("openpilot", "uses", "cereal", "2017-01-01"),
            ("openpilot", "follows", "ISO26262", "2018-01-01"),
            ("panda", "enforces", "safety_limits", "2017-01-01"),
            ("openpilot", "supports", "300+_cars", "2024-01-01"),
            ("selfdrive", "uses", "Python", "2017-01-01"),
            ("safety_code", "follows", "MISRA_C_2012", "2018-01-01"),
        ]
        for subj, pred, val, vf in facts:
            result = timed(
                f"track_fact({subj} {pred} {val})",
                track_fact(subj, pred, val, valid_from=vf),
            )
            assert "Fact recorded" in result

    def test_02_query_facts(self):
        from mcp_server.tools.kg_tools import query_facts

        result = timed("query_facts('openpilot')", query_facts("openpilot"))
        assert any(w in result for w in ["panda", "cereal", "ISO26262"])

    def test_03_query_timeline(self):
        from mcp_server.tools.kg_tools import query_facts

        result = timed("query_facts (chronological)", query_facts(
            "openpilot", chronological=True,
        ))
        assert isinstance(result, str) and len(result) > 0

    def test_04_invalidate_fact(self):
        from mcp_server.tools.kg_tools import track_fact, invalidate_fact

        timed("track expiring fact", track_fact(
            "openpilot", "supports", "200_cars", valid_from="2022-01-01",
        ))
        result = timed("invalidate_fact", invalidate_fact(
            "openpilot", "supports", "200_cars", ended="2024-01-01",
        ))
        assert "Invalidated" in result

    def test_05_kg_stats_via_palace_overview(self):
        from mcp_server.tools.memory_tools import palace_overview

        result = timed("palace_overview(detail=full)", palace_overview(detail="full"))
        assert isinstance(result, str) and len(result) > 0


# ═════════════════════════════════════════════════════════════════
# Phase 4 — Navigation (2 tools, 2 tests)
# ═════════════════════════════════════════════════════════════════

class TestPhase4Navigation:

    def test_01_explore_palace(self):
        from mcp_server.tools.nav_tools import explore_palace

        result = timed("explore_palace('solutions')", explore_palace("solutions"))
        assert isinstance(result, str) and len(result) > 0

    def test_02_find_bridges(self):
        from mcp_server.tools.nav_tools import find_bridges

        result = timed("find_bridges", find_bridges())
        assert isinstance(result, str) and len(result) > 0


# ═════════════════════════════════════════════════════════════════
# Phase 5 — Diary (2 tools, 3 tests)
# ═════════════════════════════════════════════════════════════════

class TestPhase5Diary:

    def test_01_write_diary_arch(self):
        from mcp_server.tools.diary_tools import write_diary

        result = timed("write_diary (architecture)", write_diary(
            "Explored openpilot codebase — key components are selfdrive "
            "(Python), panda (C safety code), cereal (IPC), and opendbc "
            "(car support databases).",
            topic="architecture",
        ))
        assert "saved" in result.lower() or "ID" in result

    def test_02_write_diary_debug(self):
        from mcp_server.tools.diary_tools import write_diary

        result = timed("write_diary (debugging)", write_diary(
            "The CI pipeline runs MISRA checks on panda safety code. "
            "Failing safety tests block merge — safety is top priority.",
            topic="debugging",
        ))
        assert "saved" in result.lower() or "ID" in result

    def test_03_read_diary(self):
        from mcp_server.tools.diary_tools import read_diary

        result = timed("read_diary", read_diary())
        assert any(w in result.lower() for w in [
            "architecture", "debugging", "diary",
        ])


# ═════════════════════════════════════════════════════════════════
# Phase 6 — Slack / Escalation (4 tools, mocked)
# ═════════════════════════════════════════════════════════════════

class TestPhase6SlackMocked:

    @patch("mcp_server.tools.chat_tools.urllib.request.urlopen")
    @patch("mcp_server.tools.chat_tools.SLACK_USER_TOKEN", "xoxp-test")
    def test_01_check_recent_chat(self, mock_urlopen):
        import json

        body = json.dumps({
            "ok": True,
            "messages": {"matches": [
                {
                    "username": "george",
                    "text": "The lateral planner uses MPC now",
                    "channel": {"name": "driving"},
                },
                {
                    "username": "harald",
                    "text": "Steering torque limits are in panda safety",
                    "channel": {"name": "safety"},
                },
            ]},
        }).encode()
        mock_urlopen.return_value.__enter__ = lambda s: MagicMock(
            read=lambda: body,
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        from mcp_server.tools.chat_tools import check_recent_chat

        result = timed("check_recent_chat", check_recent_chat("steering torque"))
        assert any(w in result.lower() for w in ["lateral", "steering"])

    @patch("mcp_server.tools.chat_tools.urllib.request.urlopen")
    @patch("mcp_server.tools.chat_tools.SLACK_DEFAULT_CHANNEL", "C_TEST")
    @patch("mcp_server.tools.chat_tools.SLACK_BOT_TOKEN", "xoxb-test")
    def test_02_ask_team(self, mock_urlopen):
        import json

        body = json.dumps({"ok": True}).encode()
        mock_urlopen.return_value.__enter__ = lambda s: MagicMock(
            read=lambda: body,
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        from mcp_server.tools.chat_tools import ask_team

        result = timed("ask_team", ask_team(
            "What is the maximum steering torque allowed by panda safety?",
        ))
        assert "posted" in result.lower()

    @patch("mcp_server.tools.escalation.urllib.request.urlopen")
    @patch("mcp_server.tools.escalation.ESCALATION_CHANNEL", "C_ESC")
    @patch("mcp_server.tools.escalation.SLACK_BOT_TOKEN", "xoxb-test")
    def test_03_escalate_to_human(self, mock_urlopen):
        import json

        body = json.dumps({"ok": True}).encode()
        mock_urlopen.return_value.__enter__ = lambda s: MagicMock(
            read=lambda: body,
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        from mcp_server.tools.escalation import escalate_to_human

        result = timed("escalate_to_human", escalate_to_human(
            "def apply_steer_torque(torque): ...",
            "What are the ISO11270 torque limits for lateral control?",
        ))
        assert "successfully" in result.lower() or "sent" in result.lower()

    @patch("mcp_server.tools.slack_ingest_tools._ALLOWED_CHANNELS", set())
    @patch("mcp_server.tools.slack_ingest_tools._fetch_history")
    @patch("mcp_server.tools.slack_ingest_tools.SLACK_BOT_TOKEN", "xoxb-test")
    def test_04_ingest_slack_channel(self, mock_fetch):
        mock_fetch.return_value = [
            {"user": "U001", "text": "The new lateral planner handles curves better", "ts": "1700000000.000"},
            {"user": "U002", "text": "Does it work on sharp highway ramps?", "ts": "1700000001.000"},
            {"user": "U001", "text": "Yes, tested on I-280 ramps — torque limit is the bottleneck", "ts": "1700000002.000"},
            {"user": "U003", "text": "Decision: increase torque limit to 2.5 Nm on supported cars", "ts": "1700000003.000"},
        ]

        from mcp_server.tools.slack_ingest_tools import ingest_slack_channel

        result = timed("ingest_slack_channel", ingest_slack_channel("C0123TEST"))
        assert any(w in result.lower() for w in [
            "fetched", "messages", "ingested", "stories",
        ])


# ═════════════════════════════════════════════════════════════════
# Phase 7 — Verification: imported content actually searchable
# ═════════════════════════════════════════════════════════════════

class TestPhase7Verification:

    def test_01_verify_panda_safety(self):
        from mcp_server.tools.memory_tools import search_memory

        result = timed("verify: panda safety", search_memory(
            "panda safety limits steering",
        ))
        assert any(w in result.lower() for w in [
            "panda", "safety", "steering", "torque",
        ]), f"Expected panda/safety content, got: {result[:300]}"

    def test_02_verify_contributing(self):
        from mcp_server.tools.memory_tools import search_memory

        result = timed("verify: contributing", search_memory(
            "contributing guidelines pull request merge",
        ))
        assert any(w in result.lower() for w in [
            "pull", "contribut", "merge", "pr",
        ])

    def test_03_verify_limitations(self):
        from mcp_server.tools.memory_tools import search_memory

        result = timed("verify: limitations", search_memory(
            "automated lane centering limitations weather visibility",
        ))
        assert any(w in result.lower() for w in [
            "visibility", "rain", "weather", "lane", "limit",
        ])

    def test_04_verify_kg(self):
        from mcp_server.tools.kg_tools import query_facts

        result = timed("verify: KG openpilot", query_facts("openpilot"))
        assert any(w in result for w in [
            "panda", "cereal", "ISO26262",
        ])

    def test_05_final_overview(self):
        from mcp_server.tools.memory_tools import palace_overview

        result = timed("verify: final overview", palace_overview(detail="full"))
        print("\n    === Final Palace State ===")
        for line in result.splitlines()[:10]:
            print(f"    {line}")
