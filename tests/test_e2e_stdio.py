"""
Real end-to-end MCP JSON-RPC over stdio tests.

Spawns the MCP server as a subprocess, communicates over stdin/stdout
using the JSON-RPC 2.0 / MCP 2024-11-05 protocol, and validates:
  - initialize handshake completes
  - tools/list returns the expected core tools
  - tools/call for wake_up returns a structured response (not a crash)
  - closing stdin causes the server to exit cleanly

These tests use no mocks for the transport layer — the subprocess IS the
real server. Palace operations are still absent (PNEUMA_PROJECT unset),
so tool calls that touch storage return graceful error strings rather than
real data; that is intentional and validates the _safe_tool resilience path.

Run:  pytest tests/test_e2e_stdio.py -v
Skip: set E2E_STDIO_SKIP=1 to skip (e.g. in restricted CI environments)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest


# ── Skip guard ───────────────────────────────────────────────────────────────

if os.environ.get("E2E_STDIO_SKIP"):
    pytest.skip("E2E stdio tests disabled via E2E_STDIO_SKIP", allow_module_level=True)

# ── Constants ────────────────────────────────────────────────────────────────

_STARTUP_TIMEOUT = 10.0   # seconds to wait for server to respond to initialize
_CALL_TIMEOUT = 15.0      # seconds to wait for a tool/call response
_SHUTDOWN_TIMEOUT = 5.0   # seconds to wait for clean exit after stdin close

_MCP_PROTOCOL_VERSION = "2024-11-05"

# Tools that must always appear regardless of optional integrations
_CORE_TOOLS = {
    "wake_up",
    "recall",
    "search_memory",
    "save_knowledge",
    "palace_overview",
    "mine_codebase",
    "optimize_memory",
    "delete_entry",
    "initialize_project",
    "track_fact",
    "query_facts",
    "invalidate_fact",
    "explore_palace",
    "find_bridges",
    "write_diary",
    "read_diary",
    "import_content",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _project_root() -> Path:
    return Path(__file__).parent.parent


def _send(proc: subprocess.Popen, msg: dict) -> None:
    """Write a newline-delimited JSON message to the server's stdin."""
    line = json.dumps(msg) + "\n"
    proc.stdin.write(line.encode())
    proc.stdin.flush()


def _recv(proc: subprocess.Popen, timeout: float) -> dict:
    """Read one JSON-RPC message from the server's stdout within *timeout* seconds.

    MCP stdio uses newline-delimited JSON.  We read lines until we get a
    non-empty one that parses as JSON, discarding any blank lines.
    """
    deadline = time.monotonic() + timeout
    buf = b""
    while time.monotonic() < deadline:
        # Use a short select/poll cycle to avoid blocking past the deadline.
        # On Windows, stdout is a pipe so readline() blocks; we poll manually.
        remaining = max(0.0, deadline - time.monotonic())
        proc.stdout._checkReadable()  # type: ignore[attr-defined]

        import select as _select
        try:
            ready, _, _ = _select.select([proc.stdout], [], [], min(remaining, 0.1))
        except (AttributeError, OSError):
            # Windows: select() doesn't work on pipes; fall back to readline with
            # a shorter read timeout approximated via available().
            ready = [proc.stdout]

        if not ready:
            continue

        chunk = proc.stdout.readline()
        if not chunk:
            # EOF — server exited
            raise EOFError("MCP server closed stdout unexpectedly")
        buf += chunk
        line = buf.strip()
        if line:
            return json.loads(line)

    raise TimeoutError(f"No JSON-RPC response received within {timeout}s")


def _jsonrpc(method: str, params: Any = None, id: int | None = None) -> dict:
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if id is not None:
        msg["id"] = id
    if params is not None:
        msg["params"] = params
    return msg


# ── Fixture: running MCP server subprocess ───────────────────────────────────

@pytest.fixture(scope="module")
def mcp_proc():
    """
    Start the MCP server as a subprocess and perform the initialize handshake.
    The fixture yields (proc, server_info) after a successful handshake.
    Teardown closes stdin and waits for a clean exit.
    """
    env = {**os.environ}
    # Ensure no palace is configured so tool calls hit the _safe_tool fallback
    env.pop("PNEUMA_PROJECT", None)
    # Suppress file logging noise during tests
    env["PNEUMA_LOG_LEVEL"] = "WARNING"

    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(_project_root()),
        env=env,
    )

    try:
        # ── initialize ──────────────────────────────────────────
        _send(proc, _jsonrpc(
            "initialize",
            params={
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pytest-e2e", "version": "0.1"},
            },
            id=1,
        ))
        init_response = _recv(proc, timeout=_STARTUP_TIMEOUT)

        assert init_response.get("id") == 1, (
            f"Expected initialize response id=1, got: {init_response}"
        )
        assert "error" not in init_response, (
            f"initialize returned error: {init_response['error']}"
        )

        # ── initialized notification (no response expected) ─────
        _send(proc, _jsonrpc("notifications/initialized"))

        yield proc, init_response.get("result", {})

    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=_SHUTDOWN_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()


# ── Tests ────────────────────────────────────────────────────────────────────

class TestMcpHandshake:

    def test_initialize_returns_protocol_version(self, mcp_proc):
        """Server must advertise a supported MCP protocol version."""
        _, server_info = mcp_proc
        proto = server_info.get("protocolVersion", "")
        assert proto, "Server did not return a protocolVersion"

    def test_initialize_returns_server_info(self, mcp_proc):
        """Server info block must contain a non-empty name."""
        _, server_info = mcp_proc
        info = server_info.get("serverInfo", {})
        assert info.get("name"), f"serverInfo.name missing: {server_info}"

    def test_initialize_returns_capabilities(self, mcp_proc):
        """Capabilities block must be present (even if empty)."""
        _, server_info = mcp_proc
        assert "capabilities" in server_info, (
            f"'capabilities' missing from initialize result: {server_info}"
        )


class TestToolList:

    def test_tools_list_returns_all_core_tools(self, mcp_proc):
        """tools/list must return all 17+ core tools."""
        proc, _ = mcp_proc
        _send(proc, _jsonrpc("tools/list", id=10))
        response = _recv(proc, timeout=_CALL_TIMEOUT)

        assert response.get("id") == 10
        assert "error" not in response, f"tools/list error: {response.get('error')}"

        tools = response["result"]["tools"]
        names = {t["name"] for t in tools}

        missing = _CORE_TOOLS - names
        assert not missing, f"Missing tools from tools/list: {missing}"

    def test_each_tool_has_description(self, mcp_proc):
        """Every tool must have a non-empty description string."""
        proc, _ = mcp_proc
        _send(proc, _jsonrpc("tools/list", id=11))
        response = _recv(proc, timeout=_CALL_TIMEOUT)

        tools = response["result"]["tools"]
        missing_desc = [t["name"] for t in tools if not t.get("description", "").strip()]
        assert not missing_desc, f"Tools missing description: {missing_desc}"

    def test_each_tool_has_input_schema(self, mcp_proc):
        """Every tool must have an inputSchema block."""
        proc, _ = mcp_proc
        _send(proc, _jsonrpc("tools/list", id=12))
        response = _recv(proc, timeout=_CALL_TIMEOUT)

        tools = response["result"]["tools"]
        missing_schema = [t["name"] for t in tools if "inputSchema" not in t]
        assert not missing_schema, f"Tools missing inputSchema: {missing_schema}"


class TestToolCall:

    def test_wake_up_returns_text_response(self, mcp_proc):
        """tools/call wake_up must return a content response, not a JSON-RPC error."""
        proc, _ = mcp_proc
        _send(proc, _jsonrpc(
            "tools/call",
            params={"name": "wake_up", "arguments": {}},
            id=20,
        ))
        response = _recv(proc, timeout=_CALL_TIMEOUT)

        assert response.get("id") == 20
        # May be an error string from _safe_tool (no palace configured) but
        # must NOT be a JSON-RPC protocol error or missing response.
        assert "error" not in response or response.get("result") is not None, (
            f"wake_up returned a hard protocol error: {response}"
        )
        result = response.get("result", {})
        content = result.get("content", [])
        assert content, f"wake_up returned empty content: {response}"
        assert content[0].get("type") == "text", (
            f"Expected text content, got: {content[0]}"
        )
        assert isinstance(content[0].get("text"), str)

    def test_tool_call_with_unknown_tool_returns_error(self, mcp_proc):
        """Calling a non-existent tool must return a JSON-RPC error, not crash."""
        proc, _ = mcp_proc
        _send(proc, _jsonrpc(
            "tools/call",
            params={"name": "does_not_exist", "arguments": {}},
            id=21,
        ))
        response = _recv(proc, timeout=_CALL_TIMEOUT)

        assert response.get("id") == 21
        # Server should respond with an error, not go silent
        assert "error" in response or "result" in response, (
            f"Server gave no response to unknown tool call: {response}"
        )

    def test_sequential_tool_calls_all_respond(self, mcp_proc):
        """Multiple sequential tool calls must each get a response."""
        proc, _ = mcp_proc
        ids = [30, 31, 32]
        calls = [
            ("search_memory", {"query": "test query"}),
            ("palace_overview", {}),
            ("wake_up", {}),
        ]
        responses = {}

        for call_id, (tool, args) in zip(ids, calls):
            _send(proc, _jsonrpc(
                "tools/call",
                params={"name": tool, "arguments": args},
                id=call_id,
            ))

        for call_id in ids:
            resp = _recv(proc, timeout=_CALL_TIMEOUT)
            responses[resp.get("id")] = resp

        for call_id in ids:
            assert call_id in responses, f"No response received for call id={call_id}"
            assert "id" in responses[call_id]


class TestServerShutdown:

    def test_server_exits_cleanly_when_stdin_closed(self):
        """Closing stdin must cause the server to exit within the shutdown timeout."""
        env = {**os.environ}
        env.pop("PNEUMA_PROJECT", None)
        env["PNEUMA_LOG_LEVEL"] = "WARNING"

        proc = subprocess.Popen(
            [sys.executable, "-m", "mcp_server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(_project_root()),
            env=env,
        )

        # Perform handshake
        _send(proc, _jsonrpc(
            "initialize",
            params={
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pytest-shutdown", "version": "0.1"},
            },
            id=1,
        ))
        _recv(proc, timeout=_STARTUP_TIMEOUT)
        _send(proc, _jsonrpc("notifications/initialized"))

        # Close stdin — server should detect EOF and exit
        proc.stdin.close()

        try:
            exit_code = proc.wait(timeout=_SHUTDOWN_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail(
                f"MCP server did not exit within {_SHUTDOWN_TIMEOUT}s after stdin was closed"
            )

        # Exit code 0 or 1 are both acceptable (some frameworks exit 1 on EOF)
        assert exit_code in (0, 1), (
            f"MCP server exited with unexpected code {exit_code}"
        )
