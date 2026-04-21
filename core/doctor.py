"""
Pneuma doctor — verify installation and configuration.
Checks palace, MCP server, environment, IDE configs, and Slack.
"""

import json
import os
import sys
from pathlib import Path

# ── Result helpers ───────────────────────────────────────────────

try:
    "✓✗⚠".encode(sys.stdout.encoding or "utf-8")
    _PASS, _FAIL, _WARN = "✓", "✗", "⚠"
except (UnicodeEncodeError, LookupError):
    _PASS, _FAIL, _WARN = "[OK]  ", "[FAIL]", "[WARN]"


def _ok(msg: str) -> bool:
    print(f"  {_PASS} {msg}")
    return True


def _fail(msg: str, fix: str = "") -> bool:
    print(f"  {_FAIL} {msg}")
    if fix:
        print(f"    → {fix}")
    return False


def _warn(msg: str, fix: str = "") -> bool:
    print(f"  {_WARN} {msg}")
    if fix:
        print(f"    → {fix}")
    return True  # warnings don't count as failures


# ── Individual checks ────────────────────────────────────────────

def check_palace() -> bool:
    """Verify project is registered and palace data exists."""
    from core.registry import resolve_project

    proj = resolve_project()
    ok = True

    if not proj:
        ok = _fail(
            "No registered project found for current directory",
            "Run: pneuma init /path/to/your/project",
        )
        return ok

    _ok(f"Project registered: {proj['project_path']}")
    _ok(f"Palace directory: {proj['palace_dir']}")

    palace_path = Path(proj["palace_path"])
    if not palace_path.exists():
        ok = _fail(
            f"Palace data directory not found: {palace_path}",
            "Run: pneuma init",
        )
    else:
        _ok(f"Palace data exists: {palace_path}")

    manifest = Path(proj["palace_dir"]) / "palace_manifest.json"
    if not manifest.exists():
        ok = _fail(
            "No palace_manifest.json found",
            "Run: pneuma init /path/to/your/project",
        ) and ok
    else:
        try:
            with open(manifest) as f:
                data = json.load(f)
            wings = len(data.get("wings", []))
            _ok(f"Palace manifest valid ({wings} wings configured)")
        except (json.JSONDecodeError, OSError) as e:
            ok = _fail(f"Palace manifest unreadable: {e}")

    return ok


def check_env() -> bool:
    """Verify .env and environment variables."""
    ok = True

    # .env can be in CWD (project dir) OR in the Pneuma install dir
    env_file = Path(".env")
    pneuma_root = Path(__file__).resolve().parent.parent
    pneuma_env = pneuma_root / ".env"

    if env_file.exists():
        _ok(".env file found in current directory")
    elif pneuma_env.exists():
        _ok(f".env file found in Pneuma install: {pneuma_env}")
    else:
        _warn(
            "No .env file found",
            "Only needed for Slack — copy .env.example to .env in the Pneuma install directory",
        )

    # PNEUMA_PROJECT is set in MCP config, not in the terminal.
    # Check the IDE config instead of the current env.
    project_env = os.getenv("PNEUMA_PROJECT")
    if project_env:
        _ok(f"PNEUMA_PROJECT set: {project_env}")
    else:
        # Check if it's configured in .vscode/mcp.json
        vscode_path = Path(".vscode/mcp.json")
        found_in_config = False
        if vscode_path.exists():
            try:
                with open(vscode_path) as f:
                    cfg = json.load(f)
                pneuma_cfg = cfg.get("servers", {}).get("pneuma", {})
                cfg_project = pneuma_cfg.get("env", {}).get("PNEUMA_PROJECT", "")
                if cfg_project:
                    _ok(f"PNEUMA_PROJECT configured in .vscode/mcp.json: {cfg_project}")
                    found_in_config = True
            except (json.JSONDecodeError, OSError):
                pass
        if not found_in_config:
            _warn(
                "PNEUMA_PROJECT not set in env or IDE config",
                "Run: pneuma setup vscode  (from your project directory)",
            )

    return ok


def check_mcp_server() -> bool:
    """Verify the MCP server module can be imported."""
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: F401
        _ok("mcp package importable")
    except ImportError:
        return _fail(
            "Cannot import mcp package",
            "Run: pip install -e .",
        )

    try:
        import mcp_server.server  # noqa: F401
        _ok("MCP server module importable")
    except Exception as e:
        return _fail(f"MCP server import failed: {e}")

    return True


def check_ide_configs() -> bool:
    """Check for IDE config files in the current directory."""
    found_any = False

    # VS Code
    vscode_path = Path(".vscode/mcp.json")
    if vscode_path.exists():
        found_any = True
        try:
            with open(vscode_path) as f:
                cfg = json.load(f)
            servers = cfg.get("servers", {})
            if "pneuma" not in servers:
                _warn(
                    "VS Code mcp.json exists but has no 'pneuma' entry",
                    "Run: pneuma setup vscode",
                )
            else:
                entry = servers["pneuma"]
                cmd = entry.get("command", "")
                if cmd and not Path(cmd).exists():
                    _warn(
                        f"VS Code config points to missing Python: {cmd}",
                        "Run: pneuma setup vscode  (to regenerate with current paths)",
                    )
                else:
                    _ok("VS Code mcp.json configured for pneuma")
        except (json.JSONDecodeError, OSError) as e:
            _fail(f"VS Code mcp.json unreadable: {e}")
    else:
        _warn("No .vscode/mcp.json found", "Run: pneuma setup vscode")

    # Claude Code
    claude_code_path = Path(".mcp.json")
    if claude_code_path.exists():
        found_any = True
        try:
            with open(claude_code_path) as f:
                cfg = json.load(f)
            servers = cfg.get("mcpServers", {})
            if "pneuma" not in servers:
                _warn(
                    ".mcp.json exists but has no 'pneuma' entry",
                    "Run: pneuma setup claude-code",
                )
            else:
                entry = servers["pneuma"]
                cmd = entry.get("command", "")
                if cmd and not Path(cmd).exists():
                    _warn(
                        f"Claude Code .mcp.json points to missing Python: {cmd}",
                        "Run: pneuma setup claude-code  (to regenerate with current paths)",
                    )
                else:
                    _ok("Claude Code .mcp.json configured for pneuma")
        except (json.JSONDecodeError, OSError) as e:
            _fail(f".mcp.json unreadable: {e}")
    else:
        _warn("No .mcp.json found", "Run: pneuma setup claude-code")

    if not found_any:
        _warn(
            "No IDE configs detected",
            "Run: pneuma setup vscode  |  pneuma setup cursor  |  pneuma setup claude-code",
        )

    return True  # IDE config is advisory, not a hard failure


def check_slack() -> bool:
    """If Slack is configured, verify the token works and audit scopes."""
    token = os.getenv("SLACK_BOT_TOKEN", "")
    if not token:
        _warn("SLACK_BOT_TOKEN not set — Slack tools will not register (this is fine if you don't use Slack)")
        return True

    _ok("SLACK_BOT_TOKEN is set")

    # Check other required Slack vars
    missing = []
    for var in ("SLACK_SIGNING_SECRET", "SLACK_APP_TOKEN"):
        if not os.getenv(var, ""):
            missing.append(var)
    if missing:
        _warn(f"Slack vars not set: {', '.join(missing)}")

    if not os.getenv("ESCALATION_CHANNEL", ""):
        _warn("ESCALATION_CHANNEL not set — escalate_to_human won't know where to post")

    # Try auth_test
    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError:
        return _fail(
            "slack-sdk not installed",
            "Run: pip install -e .",
        )

    client = WebClient(token=token)
    try:
        auth = client.auth_test()
        _ok(f"Slack auth OK — bot: {auth['user']}, team: {auth['team']}")
    except SlackApiError as e:
        return _fail(
            f"Slack auth failed: {e}",
            "Check SLACK_BOT_TOKEN in .env",
        )

    # Scope audit (folded from scripts/audit_bot_permissions.py)
    return _audit_slack_scopes(client, SlackApiError)


def check_teams() -> bool:
    """If Teams is configured, verify credentials and webhook URLs."""
    client_id = os.getenv("TEAMS_CLIENT_ID", "")
    if not client_id:
        _warn("TEAMS_CLIENT_ID not set — Teams tools will not register (fine if you don't use Teams)")
        return True

    _ok("TEAMS_CLIENT_ID is set")

    missing = []
    for var in ("TEAMS_CLIENT_SECRET", "TEAMS_TENANT_ID", "TEAMS_TEAM_ID"):
        if not os.getenv(var, ""):
            missing.append(var)
    if missing:
        _warn(f"Teams vars not set: {', '.join(missing)}", "See docs/teams-setup.md")

    if not os.getenv("TEAMS_ALLOWED_CHANNEL_IDS", ""):
        _warn("TEAMS_ALLOWED_CHANNEL_IDS not set — ingest_teams_channel will reject all channels")

    if not os.getenv("TEAMS_DEFAULT_WEBHOOK_URL", ""):
        _warn("TEAMS_DEFAULT_WEBHOOK_URL not set — ask_teams_channel will be unavailable")

    if not os.getenv("TEAMS_ESCALATION_WEBHOOK_URL", ""):
        _warn("TEAMS_ESCALATION_WEBHOOK_URL not set — escalate_to_teams will fall back to default webhook")

    # Quick token acquisition check
    client_secret = os.getenv("TEAMS_CLIENT_SECRET", "")
    tenant_id = os.getenv("TEAMS_TENANT_ID", "")
    if client_id and client_secret and tenant_id:
        import urllib.parse
        import urllib.request
        import json as _json
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }).encode()
        req = urllib.request.Request(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = _json.loads(resp.read())
            if "access_token" in result:
                _ok("Teams app credentials valid — token acquired successfully")
            else:
                _fail(
                    f"Teams auth failed: {result.get('error_description', result.get('error', 'unknown'))}",
                    "Check TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET, TEAMS_TENANT_ID in .env",
                )
        except Exception as exc:
            _fail(f"Teams token request failed: {exc}")

    return True


def _audit_slack_scopes(client, SlackApiError):
    """Check that the bot does NOT have dangerous scopes."""
    ok = True

    # Private channels — should fail
    try:
        client.conversations_list(types="private_channel", limit=1)
        ok = _fail(
            "Bot CAN list private channels",
            "Revoke 'groups:read' scope in Slack app settings",
        )
    except SlackApiError as e:
        if "missing_scope" in str(e):
            _ok("Bot cannot access private channels")

    # DMs — should fail
    try:
        client.conversations_list(types="im", limit=1)
        ok = _fail(
            "Bot CAN list DMs",
            "Revoke 'im:read' scope in Slack app settings",
        ) and ok
    except SlackApiError as e:
        if "missing_scope" in str(e):
            _ok("Bot cannot access DMs")

    return ok


# ── Runner ───────────────────────────────────────────────────────

def run_doctor() -> bool:
    """Run all checks and return True if no hard failures."""
    all_ok = True

    print("\nPneuma Doctor\n")

    print("Palace:")
    all_ok = check_palace() and all_ok

    print("\nEnvironment:")
    all_ok = check_env() and all_ok

    print("\nMCP Server:")
    all_ok = check_mcp_server() and all_ok

    print("\nIDE Config:")
    check_ide_configs()  # advisory only

    print("\nSlack:")
    all_ok = check_slack() and all_ok

    print("\nMicrosoft Teams:")
    check_teams()  # advisory only

    print()
    if all_ok:
        print("All checks passed.")
    else:
        print("Some checks failed — see above for fixes.")

    return all_ok
