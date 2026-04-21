"""
Tests for mcp_server/tools/teams_ingest_tools.py

All network calls are mocked — no real Azure AD or Graph API traffic.
"""

import asyncio
import json
from unittest.mock import patch, MagicMock

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_message(text: str, user_id: str = "user1", msg_type: str = "message") -> dict:
    return {
        "messageType": msg_type,
        "body": {"content": text, "contentType": "text"},
        "from": {"user": {"id": user_id, "displayName": "Dev User"}},
        "createdDateTime": "2026-04-20T10:00:00Z",
    }


_TEAMS_ENV = {
    "TEAMS_CLIENT_ID": "test-client-id",
    "TEAMS_CLIENT_SECRET": "test-secret",
    "TEAMS_TENANT_ID": "test-tenant",
    "TEAMS_TEAM_ID": "test-team-id",
    "TEAMS_ALLOWED_CHANNEL_IDS": "chan-1,chan-2",
}

_GOOD_TOKEN_RESPONSE = json.dumps({
    "access_token": "fake-token",
    "expires_in": 3600,
}).encode()


# ── Configuration guard ───────────────────────────────────────────────────────

class TestIngestConfiguration:

    def test_missing_credentials_returns_error(self):
        with patch.dict("os.environ", {
            "TEAMS_CLIENT_ID": "", "TEAMS_CLIENT_SECRET": "", "TEAMS_TENANT_ID": ""
        }, clear=False):
            # reload env vars in the module
            import importlib
            import mcp_server.tools.teams_ingest_tools as mod
            importlib.reload(mod)

            result = _run(mod.ingest_teams_channel("chan-1"))
            assert "not configured" in result.lower()

    def test_missing_team_id_returns_error(self):
        with patch.dict("os.environ", {**_TEAMS_ENV, "TEAMS_TEAM_ID": ""}, clear=False):
            import importlib
            import mcp_server.tools.teams_ingest_tools as mod
            importlib.reload(mod)

            result = _run(mod.ingest_teams_channel("chan-1", team_id=""))
            assert "TEAMS_TEAM_ID" in result

    def test_channel_not_in_allowed_list_returns_error(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_ingest_tools as mod
            importlib.reload(mod)

            result = _run(mod.ingest_teams_channel("chan-NOT-ALLOWED", team_id="test-team-id"))
            assert "allowed" in result.lower()

    def test_allowed_channels_empty_skips_check(self):
        """When TEAMS_ALLOWED_CHANNEL_IDS is empty, any channel is accepted."""
        env = {**_TEAMS_ENV, "TEAMS_ALLOWED_CHANNEL_IDS": ""}
        with patch.dict("os.environ", env, clear=False):
            import importlib
            import mcp_server.tools.teams_ingest_tools as mod
            importlib.reload(mod)

            with patch.object(mod, "_fetch_channel_messages", return_value=[]):
                result = _run(mod.ingest_teams_channel("any-channel", team_id="test-team-id"))
            assert "No messages" in result


# ── Token acquisition ─────────────────────────────────────────────────────────

class TestTokenAcquisition:

    def test_token_is_cached(self):
        import mcp_server.tools.teams_ingest_tools as mod

        mock_resp = MagicMock()
        mock_resp.read.return_value = _GOOD_TOKEN_RESPONSE
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        mod._token_cache.clear()

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            token1 = mod._get_access_token()
            token2 = mod._get_access_token()

        assert token1 == "fake-token"
        assert token2 == "fake-token"
        # Second call should use cache — urlopen called only once
        assert mock_open.call_count == 1

    def test_token_refreshed_when_expired(self):
        import time
        import mcp_server.tools.teams_ingest_tools as mod

        mod._token_cache["access_token"] = "old-token"
        mod._token_cache["expires_at"] = time.time() - 10  # already expired

        mock_resp = MagicMock()
        mock_resp.read.return_value = _GOOD_TOKEN_RESPONSE
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            token = mod._get_access_token()

        assert token == "fake-token"

    def test_auth_error_raises_runtime_error(self):
        import mcp_server.tools.teams_ingest_tools as mod

        error_response = json.dumps({
            "error": "invalid_client",
            "error_description": "Invalid client secret",
        }).encode()

        mod._token_cache.clear()

        mock_resp = MagicMock()
        mock_resp.read.return_value = error_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="Teams auth error"):
                mod._get_access_token()


# ── Message fetching ──────────────────────────────────────────────────────────

class TestFetchChannelMessages:

    def _mock_graph_response(self, messages: list) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"value": messages}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_returns_messages(self):
        import mcp_server.tools.teams_ingest_tools as mod

        messages = [_make_message("Bug in the auth module"), _make_message("Fixed: added retry logic")]
        with patch.object(mod, "_get_access_token", return_value="fake-token"):
            with patch("urllib.request.urlopen", return_value=self._mock_graph_response(messages)):
                result = mod._fetch_channel_messages("team-1", "chan-1", "2026-01-01T00:00:00Z", 10)

        assert isinstance(result, list)
        assert len(result) == 2

    def test_api_error_returns_string(self):
        import mcp_server.tools.teams_ingest_tools as mod

        with patch.object(mod, "_get_access_token", side_effect=RuntimeError("auth failed")):
            result = mod._fetch_channel_messages("team-1", "chan-1", "2026-01-01T00:00:00Z", 10)

        assert isinstance(result, str)
        assert "auth failed" in result

    def test_respects_limit(self):
        import mcp_server.tools.teams_ingest_tools as mod

        messages = [_make_message(f"message {i}") for i in range(100)]
        with patch.object(mod, "_get_access_token", return_value="fake-token"):
            with patch("urllib.request.urlopen", return_value=self._mock_graph_response(messages)):
                result = mod._fetch_channel_messages("team-1", "chan-1", "2026-01-01T00:00:00Z", limit=5)

        assert isinstance(result, list)
        assert len(result) <= 5


# ── Full ingestion pipeline ───────────────────────────────────────────────────

class TestIngestPipeline:

    def _patch_fetch(self, messages):
        import mcp_server.tools.teams_ingest_tools as mod
        return patch.object(mod, "_fetch_channel_messages", return_value=messages)

    def test_no_messages_returns_info(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_ingest_tools as mod
            importlib.reload(mod)

            with self._patch_fetch([]):
                result = _run(mod.ingest_teams_channel("chan-1", team_id="test-team-id"))
            assert "No messages" in result

    def test_all_noise_returns_info(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_ingest_tools as mod
            importlib.reload(mod)

            noisy = [_make_message("hi"), _make_message("lol"), _make_message("good morning")]
            with self._patch_fetch(noisy):
                result = _run(mod.ingest_teams_channel("chan-1", team_id="test-team-id"))
            assert "noise" in result.lower()

    def test_skips_non_message_types(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_ingest_tools as mod
            importlib.reload(mod)

            messages = [
                _make_message("System event", msg_type="systemEventMessage"),
                _make_message("Bug in the payment module — fixed by adding retry logic"),
            ]
            with self._patch_fetch(messages):
                with patch("chat_bot.injector.inject_stories", return_value={"stored": 1, "errors": []}):
                    result = _run(mod.ingest_teams_channel("chan-1", team_id="test-team-id"))
            # Should process only the real message
            assert "Entries stored" in result or "noise" in result.lower()

    def test_successful_ingestion_summary(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_ingest_tools as mod
            importlib.reload(mod)

            messages = [
                _make_message("Bug: auth tokens expire after 5 min — how to fix?"),
                _make_message("Fixed: increase TTL to 24h in the config/auth.yaml"),
            ]
            with self._patch_fetch(messages):
                with patch("chat_bot.injector.inject_stories", return_value={"stored": 1, "errors": []}):
                    result = _run(mod.ingest_teams_channel("chan-1", team_id="test-team-id"))

            assert "chan-1" in result
            assert "Messages fetched" in result
            assert "Entries stored" in result

    def test_graph_api_error_propagates(self):
        with patch.dict("os.environ", _TEAMS_ENV, clear=False):
            import importlib
            import mcp_server.tools.teams_ingest_tools as mod
            importlib.reload(mod)

            with self._patch_fetch("Graph API error: forbidden"):
                result = _run(mod.ingest_teams_channel("chan-1", team_id="test-team-id"))
            assert "Graph API error" in result


# ── HTML stripping ────────────────────────────────────────────────────────────

class TestStripHtml:

    def test_removes_tags(self):
        from mcp_server.tools.teams_ingest_tools import _strip_html
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello  world"

    def test_plain_text_unchanged(self):
        from mcp_server.tools.teams_ingest_tools import _strip_html
        assert _strip_html("plain text") == "plain text"

    def test_empty_string(self):
        from mcp_server.tools.teams_ingest_tools import _strip_html
        assert _strip_html("") == ""

    def test_only_tags_returns_empty(self):
        from mcp_server.tools.teams_ingest_tools import _strip_html
        assert _strip_html("<br/><hr/>").strip() == ""
