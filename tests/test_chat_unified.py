"""Tests for mcp_server/tools/chat_unified — platform-agnostic dispatch."""

import asyncio
from unittest.mock import patch, AsyncMock

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Platform resolution ─────────────────────────────────────────────────────

class TestResolvePlatform:
    def test_auto_picks_slack_when_configured(self):
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test", "TEAMS_CLIENT_ID": ""}):
            import importlib
            import mcp_server.tools.chat_unified as mod
            importlib.reload(mod)
            p, err = mod._resolve_platform("auto")
            assert p == "slack"
            assert not err

    def test_auto_picks_teams_when_only_teams_configured(self):
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "", "TEAMS_CLIENT_ID": "app-id"}):
            import importlib
            import mcp_server.tools.chat_unified as mod
            importlib.reload(mod)
            p, err = mod._resolve_platform("auto")
            assert p == "teams"
            assert not err

    def test_auto_slack_preferred_when_both_set(self):
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test", "TEAMS_CLIENT_ID": "app-id"}):
            import importlib
            import mcp_server.tools.chat_unified as mod
            importlib.reload(mod)
            p, err = mod._resolve_platform("auto")
            assert p == "slack"

    def test_auto_no_platform_configured_returns_error(self):
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "", "TEAMS_CLIENT_ID": ""}):
            import importlib
            import mcp_server.tools.chat_unified as mod
            importlib.reload(mod)
            p, err = mod._resolve_platform("auto")
            assert p == ""
            assert "no chat platform" in err.lower()

    def test_explicit_slack_not_configured_errors(self):
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "", "TEAMS_CLIENT_ID": "app-id"}):
            import importlib
            import mcp_server.tools.chat_unified as mod
            importlib.reload(mod)
            p, err = mod._resolve_platform("slack")
            assert p == ""
            assert "Slack" in err

    def test_explicit_teams_not_configured_errors(self):
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test", "TEAMS_CLIENT_ID": ""}):
            import importlib
            import mcp_server.tools.chat_unified as mod
            importlib.reload(mod)
            p, err = mod._resolve_platform("teams")
            assert p == ""
            assert "Teams" in err

    def test_unknown_platform(self):
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test"}):
            import importlib
            import mcp_server.tools.chat_unified as mod
            importlib.reload(mod)
            p, err = mod._resolve_platform("discord")
            assert p == ""
            assert "Unknown" in err


# ── Dispatch ────────────────────────────────────────────────────────────────

class TestDispatch:
    def test_check_recent_chat_routes_to_slack(self):
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test", "TEAMS_CLIENT_ID": ""}):
            import importlib
            import mcp_server.tools.chat_unified as mod
            importlib.reload(mod)

            with patch("mcp_server.tools.chat_tools.check_recent_chat",
                       new=AsyncMock(return_value="slack-result")):
                result = _run(mod.check_recent_chat("auth"))
                assert result == "slack-result"

    def test_check_recent_chat_routes_to_teams(self):
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "", "TEAMS_CLIENT_ID": "app"}):
            import importlib
            import mcp_server.tools.chat_unified as mod
            importlib.reload(mod)

            with patch("mcp_server.tools.teams_chat_tools.check_recent_teams_chat",
                       new=AsyncMock(return_value="teams-result")):
                result = _run(mod.check_recent_chat("auth"))
                assert result == "teams-result"

    def test_ingest_chat_channel_requires_explicit_platform(self):
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test"}):
            import importlib
            import mcp_server.tools.chat_unified as mod
            importlib.reload(mod)

            result = _run(mod.ingest_chat_channel("C123", platform="auto"))
            assert "explicit platform" in result.lower()

    def test_escalate_normalizes_slack_arg_order(self):
        """Slack's internal signature is (code_context, question);
        unified wrapper uses (question, code_context)."""
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test"}):
            import importlib
            import mcp_server.tools.chat_unified as mod
            importlib.reload(mod)

            captured = {}

            async def fake_slack_escalate(code_context, question):
                captured["code_context"] = code_context
                captured["question"] = question
                return "ok"

            with patch("mcp_server.tools.escalation.escalate_to_human", new=fake_slack_escalate):
                _run(mod.escalate_to_human(question="why?", code_context="class X: ..."))

            assert captured["question"] == "why?"
            assert captured["code_context"] == "class X: ..."
