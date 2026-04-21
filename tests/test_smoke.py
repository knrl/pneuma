"""Smoke tests — verify the MCP server boots and exposes all tools.

Spawns ``python -m mcp_server`` as a subprocess, sends JSON-RPC messages
over stdio, and checks the responses.  Uses a temporary project directory
so the real ~/.pneuma is untouched.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest


def _send_and_receive(proc, message: dict, timeout: float = 15.0) -> dict:
    """
    Send a JSON-RPC message to the subprocess and read one response line.
    Uses a thread with a timeout for the blocking readline.
    """
    payload = json.dumps(message) + "\n"
    proc.stdin.write(payload)
    proc.stdin.flush()

    result = {"line": None, "error": None}

    def _read():
        try:
            result["line"] = proc.stdout.readline()
        except Exception as exc:
            result["error"] = exc

    reader = threading.Thread(target=_read, daemon=True)
    reader.start()
    reader.join(timeout=timeout)

    if reader.is_alive():
        pytest.fail(f"Server did not respond within {timeout}s")

    if result["error"]:
        raise result["error"]

    line = result["line"]
    if not line:
        stderr_out = ""
        try:
            stderr_out = proc.stderr.read(4096)
        except Exception:
            pass
        pytest.fail(f"Server returned empty response. stderr: {stderr_out}")

    return json.loads(line)


@pytest.fixture(scope="module")
def mcp_server():
    """
    Start the MCP server subprocess with PNEUMA_PROJECT pointed at
    a temporary project directory.  Yields the Popen handle.
    """
    tmpdir = tempfile.mkdtemp(prefix="pneuma-smoke-")
    pneuma_home = os.path.join(tmpdir, "pneuma_home")
    project_dir = os.path.join(tmpdir, "fake-project")
    os.makedirs(pneuma_home)
    os.makedirs(project_dir)

    # Pre-register the project by calling the registry directly
    env = os.environ.copy()
    env["PNEUMA_HOME"] = pneuma_home
    env["PNEUMA_PROJECT"] = project_dir
    # Remove SLACK_BOT_TOKEN to test without Slack tools
    env.pop("SLACK_BOT_TOKEN", None)

    # Register the project so configure() can find it.
    # Use repr() so Windows paths with backslashes or 8.3 short names
    # (e.g. MEHMET~1) are safely embedded as string literals in the -c script.
    reg_script = (
        "import os; os.environ['PNEUMA_HOME'] = {home};"
        "from core.registry import register_project;"
        "register_project({proj})"
    ).format(home=repr(pneuma_home), proj=repr(project_dir))

    subprocess.run(
        [sys.executable, "-c", reg_script],
        cwd=str(Path(__file__).resolve().parent.parent),
        env=env,
        check=True,
        capture_output=True,
    )

    # Start the MCP server
    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path(__file__).resolve().parent.parent),
        env=env,
        text=True,
        bufsize=1,  # line-buffered
    )

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(tmpdir, ignore_errors=True)


# ── Expected core tools (always registered, no Slack token) ──
CORE_TOOLS = {
    "wake_up",
    "recall",
    "search_memory",
    "save_knowledge",
    "palace_overview",
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

SLACK_TOOLS = {
    "check_recent_chat",
    "ask_team",
    "ingest_slack_channel",
    "escalate_to_human",
}


class TestMCPServerSmoke:

    def test_server_boots_and_responds(self, mcp_server):
        """Server responds to JSON-RPC initialize with capabilities."""
        response = _send_and_receive(mcp_server, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pneuma-test", "version": "0.1"},
            },
        })

        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == 1
        assert "result" in response, f"Expected result, got: {response}"
        assert "capabilities" in response["result"]

    def test_all_tools_registered(self, mcp_server):
        """After initialize, tools/list returns all expected tool names."""
        # Must initialize first (may already be done by previous test,
        # but the server should handle it)
        init_resp = _send_and_receive(mcp_server, {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pneuma-test", "version": "0.1"},
            },
        })

        # Send notifications/initialized to complete handshake
        notify = json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }) + "\n"
        mcp_server.stdin.write(notify)
        mcp_server.stdin.flush()

        # Now request tools/list
        response = _send_and_receive(mcp_server, {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/list",
            "params": {},
        })

        assert "result" in response, f"Expected result, got: {response}"
        tools = response["result"].get("tools", [])
        tool_names = {t["name"] for t in tools}

        # Core tools must always be present
        missing = CORE_TOOLS - tool_names
        assert not missing, f"Missing core tools: {missing}"

        # Total should be 17 core (no Slack) or 21 (with Slack)
        # The server loads .env from disk, so Slack tools may be present
        # if SLACK_BOT_TOKEN is in the .env file — that's valid behavior
        assert len(tool_names) in (17, 21), (
            f"Expected 17 or 21 tools, got {len(tool_names)}: {tool_names}"
        )
