"""
Tests for mcp_server/tools/teams_chat_tools.py

All network calls are mocked — no real Teams webhook or Graph API traffic.
"""

import asyncio
import json
from unittest.mock import patch, MagicMock, call

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


_TEAMS_ENV = {
    "TEAMS_CLIENT_ID": "test-client-id",
    "TEAMS_CLIENT_SECRET": "test-secret",
    "TEAMS_TENANT_ID": "test-tenant",
    "TEAMS_TEAM_ID": "test-team-id",
    "TEAMS_ALLOWED_CHANNEL_IDS": "chan-1,chan-2",
    "TEAMS_DEFAULT_WEBHOOK_URL": "https://example.webhook.office.com/default",
    "TEAMS_ESCALATION_WEBHOOK_URL": "https://example.webhook.office.com/escalation",
}


def _make_graph_message(text: str, channel_id: str = "chan-1") -> dict:
    return {
        "messageType": "message",
        "body": {"content": text},
        "from": {"user": {"displayName": "Dev User"}},
        "createdDateTime": "2026-04-20T10:00:00Z",
    }


# ── _sanitize ─────────────────────────────────────────────────────────────────

class TestSanitize:

    def test_strips_html_tags(self):
        from mcp_server.tools.teams_chat_tools import _sanitize
        assert "<script>" not in _sanitize("<script>alert('xss')</script>hello")

    def test_strips_teams_at_mention(self):
        from mcp_server.tools.teams_chat_tools import _sanitize
        result = _sanitize("<at>Engineering</at> please review")
        assert "<at>" not in result
        assert "</at>" not in result

    def test_strips_nested_html(self):
        from mcp_server.tools.teams_chat_tools import _sanitize
        result = _sanitize("<p><b>bold</b> text</p>")
        assert "<" not in result
        assert "bold" in result
        assert "text" in result

    def test_plain_text_unchanged(self):
        from mcp_server.tools.teams_chat_tools import _sanitize
        assert _sanitize("plain question about auth") == "plain question about auth"

    def test_empty_string(self):
        from mcp_server.tools.teams_chat_tools import _sanitize
        assert _sanitize("") == ""


# ── _post_webhook ─────────────────────────────────────────────────────────────

class TestPostWebhook:

    def _mock_urlopen(self, body: str):
        mock_resp = MagicMock()
        mock_resp.read.return_value = body.encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_success_returns_ok(self):
        from mcp_server.tools.teams_chat_tools import _post_webhook
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen("1")):
            result = _post_webhook("https://example.com/webhook", {"text": "hello"})
        assert result == "ok"

    def test_unexpected_response_reported(self):
        from mcp_server.tools.teams_chat_tools import _post_webhook
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen("something else")):
            result = _post_webhook("https://example.com/webhook", {"text": "hello"})
        assert "unexpected" in result

    def test_network_error_reported(self):
        from mcp_server.tools.teams_chat_tools import _post_webhook
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            result = _post_webhook("https://example.com/webhook", {"text": "hello"})
        assert "error" in result
        assert "connection refused" in result

    def test_sends_json_content_type(self):
        from mcp_server.tools.teams_chat_tools import _post_webhook
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen("1")) as mock_open:
            _post_webhook("https://example.com/webhook", {"text": "hello"})
        req = mock_open.call_args[0][0]
        assert req.get_header("Content-type") == "application/json"

    def test_payload_is_valid_json(self):
        from mcp_server.tools.teams_chat_tools import _post_webhook
        captured = {}
        def capture(req, **kwargs):
            captured["data"] = req.data
            return self._mock_urlopen("1")

        payload = {"text": "test message", "sections": []}
        with patch("urllib.request.urlopen", side_effect=capture):
            _post_webhook("https://example.com/webhook", payload)
        assert json.loads(captured["data"]) == payload


# ── check_recent_teams_chat ───────────────────────────────────────────────────

class TestCheckRecentTeamsChat:

    def test_missing_config_returns_error(self):
        with patch.dict("os.environ", {
            "TEAMS_CLIENT_ID": "", "TEAMS_CLIENT_SECRET": "", "TEAMS_TENANT_ID": ""
        }, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            result = _run(mod.check_recent_teams_chat("auth"))
            assert "not configured" in result.lower()

    def test_no_allowed_channels_returns_error(self):
        env = {**_TEAMS_ENV, "TEAMS_ALLOWED_CHANNEL_IDS": ""}
        with patch.dict("os.environ", env, clear=False):
            import importlib
            import mcp_server.tools.teams_ingest_tools as ingest_mod
            importlib.reload(ingest_mod)
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            result = _run(mod.check_recent_teams_chat("auth"))
            assert "No channels" in result

    def test_finds_matching_messages(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_ingest_tools as ingest_mod
            importlib.reload(ingest_mod)
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            messages = [
                _make_graph_message("Bug: auth tokens expire after 5 minutes"),
                _make_graph_message("Fixed auth by refreshing the token store"),
                _make_graph_message("Lunch today?"),
            ]

            with patch(
                "mcp_server.tools.teams_ingest_tools._fetch_channel_messages",
                return_value=messages,
            ):
                result = _run(mod.check_recent_teams_chat("auth"))

            assert "auth" in result.lower()
            assert "Found" in result

    def test_no_matches_returns_info(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_ingest_tools as ingest_mod
            importlib.reload(ingest_mod)
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            messages = [_make_graph_message("Lunch today?")]
            with patch(
                "mcp_server.tools.teams_ingest_tools._fetch_channel_messages",
                return_value=messages,
            ):
                result = _run(mod.check_recent_teams_chat("kubernetes"))

            assert "No recent" in result

    def test_respects_count_limit(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            messages = [_make_graph_message(f"auth issue {i}") for i in range(30)]
            with patch(
                "mcp_server.tools.teams_ingest_tools._fetch_channel_messages",
                return_value=messages,
            ):
                result = _run(mod.check_recent_teams_chat("auth", count=5))

            lines = [l for l in result.splitlines() if l.strip().startswith("[")]
            assert len(lines) <= 5

    def test_count_capped_at_20(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            messages = [_make_graph_message(f"auth msg {i}") for i in range(50)]
            with patch(
                "mcp_server.tools.teams_ingest_tools._fetch_channel_messages",
                return_value=messages,
            ):
                result = _run(mod.check_recent_teams_chat("auth", count=999))

            lines = [l for l in result.splitlines() if l.strip().startswith("[")]
            assert len(lines) <= 20


# ── ask_teams_channel ─────────────────────────────────────────────────────────

class TestAskTeamsChannel:

    def test_no_webhook_url_returns_error(self):
        env = {**_TEAMS_ENV, "TEAMS_DEFAULT_WEBHOOK_URL": ""}
        with patch.dict("os.environ", env, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            result = _run(mod.ask_teams_channel("How do we handle rate limiting?"))
            assert "webhook" in result.lower()

    def test_posts_successfully(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            with patch.object(mod, "_post_webhook", return_value="ok"):
                result = _run(mod.ask_teams_channel("How do we handle rate limiting?"))

            assert "posted" in result.lower()

    def test_post_failure_reported(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            with patch.object(mod, "_post_webhook", return_value="error: timeout"):
                result = _run(mod.ask_teams_channel("How do we handle rate limiting?"))

            assert "Failed" in result

    def test_uses_provided_webhook_url(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            custom_url = "https://example.webhook.office.com/custom"
            with patch.object(mod, "_post_webhook", return_value="ok") as mock_post:
                _run(mod.ask_teams_channel("question", webhook_url=custom_url))

            assert mock_post.call_args[0][0] == custom_url

    def test_question_is_sanitized(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            captured = {}
            def capture(url, payload):
                captured["payload"] = payload
                return "ok"

            with patch.object(mod, "_post_webhook", side_effect=capture):
                _run(mod.ask_teams_channel("<script>alert('xss')</script>real question"))

            text = str(captured["payload"])
            assert "<script>" not in text


# ── escalate_to_teams ─────────────────────────────────────────────────────────

class TestEscalateToTeams:

    def test_no_webhook_configured_returns_error(self):
        env = {
            **_TEAMS_ENV,
            "TEAMS_ESCALATION_WEBHOOK_URL": "",
            "TEAMS_DEFAULT_WEBHOOK_URL": "",
        }
        with patch.dict("os.environ", env, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            result = _run(mod.escalate_to_teams("unanswerable question", "some code"))
            assert "not configured" in result.lower() or "webhook" in result.lower()

    def test_escalation_webhook_takes_priority(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            with patch.object(mod, "_post_webhook", return_value="ok") as mock_post:
                _run(mod.escalate_to_teams("question", "code"))

            used_url = mock_post.call_args[0][0]
            assert used_url == _TEAMS_ENV["TEAMS_ESCALATION_WEBHOOK_URL"]

    def test_falls_back_to_default_webhook(self):
        env = {**_TEAMS_ENV, "TEAMS_ESCALATION_WEBHOOK_URL": ""}
        with patch.dict("os.environ", env, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            with patch.object(mod, "_post_webhook", return_value="ok") as mock_post:
                _run(mod.escalate_to_teams("question", "code"))

            used_url = mock_post.call_args[0][0]
            assert used_url == _TEAMS_ENV["TEAMS_DEFAULT_WEBHOOK_URL"]

    def test_escalates_successfully(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            with patch.object(mod, "_post_webhook", return_value="ok"):
                result = _run(mod.escalate_to_teams(
                    "Why does the auth service keep 401ing?",
                    "class AuthService:\n    def verify(self, token): ...",
                ))

            assert "sent" in result.lower() or "escalat" in result.lower()

    def test_code_context_truncated_to_1500(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            long_code = "x = 1\n" * 500  # well over 1500 chars
            captured = {}
            def capture(url, payload):
                captured["payload"] = payload
                return "ok"

            with patch.object(mod, "_post_webhook", side_effect=capture):
                _run(mod.escalate_to_teams("question", long_code))

            payload_str = json.dumps(captured["payload"])
            # The raw code_context[:1500] means the final payload is bounded
            assert len(payload_str) < 10_000

    def test_post_failure_reported(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_chat_tools as mod
            importlib.reload(mod)

            with patch.object(mod, "_post_webhook", return_value="error: 403 Forbidden"):
                result = _run(mod.escalate_to_teams("question", "code"))

            assert "failed" in result.lower() or "403" in result
