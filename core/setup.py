"""
Pneuma setup — generate IDE-specific MCP configuration.
Auto-detects Python path, project root, and MEMPALACE_HOME.
"""

import json
import os
import sys
from pathlib import Path


def detect_ides() -> list[str]:
    """Return which IDEs are detectable in the current environment.

    Detection heuristics (in priority order):
      - VS Code   : ``VSCODE_PID`` env var set, or ``.vscode/`` dir exists in CWD
      - Claude Code: ``CLAUDE_CODE_ENTRYPOINT`` env var set, or ``.mcp.json`` in CWD
      - Cursor    : ``CURSOR_TRACE_CALLS`` env var set, or ``~/.cursor/`` dir exists

    Falls back to ``["vscode"]`` when nothing is detected so the common case
    always produces a usable config.
    """
    found: list[str] = []

    # VS Code
    if os.environ.get("VSCODE_PID") or Path(".vscode").is_dir():
        found.append("vscode")

    # Claude Code
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") or Path(".mcp.json").exists():
        found.append("claude-code")

    # Cursor
    cursor_home = Path.home() / ".cursor"
    if os.environ.get("CURSOR_TRACE_CALLS") or cursor_home.is_dir():
        found.append("cursor")

    return found if found else ["vscode"]


def _detect_paths() -> dict:
    """Auto-detect paths for MCP config generation."""
    python_path = sys.executable
    # Project root is the parent of the `core/` package (Pneuma's install dir)
    pneuma_root = str(Path(__file__).resolve().parents[1])

    # Detect the user's project (CWD or PNEUMA_PROJECT env var)
    from core.registry import resolve_project
    proj = resolve_project()
    user_project = proj["project_path"] if proj else None

    return {
        "python": python_path,
        "pneuma_root": pneuma_root,
        "user_project": user_project,
    }


def _build_server_entry(paths: dict) -> dict:
    """Build the Pneuma MCP server config entry."""
    entry = {
        "type": "stdio",
        "command": paths["python"],
        "args": ["-m", "mcp_server.server"],
        "cwd": paths["pneuma_root"],
    }
    if paths.get("user_project"):
        entry["env"] = {"PNEUMA_PROJECT": paths["user_project"]}
    return entry


def _verify_server() -> bool:
    """Quick check that the MCP server module can be imported."""
    try:
        import mcp_server.server  # noqa: F401
        return True
    except Exception:
        return False


def setup_vscode() -> str:
    """Generate or update .vscode/mcp.json with Pneuma server entry.

    Returns the path written to.
    """
    paths = _detect_paths()
    entry = _build_server_entry(paths)

    vscode_dir = Path(".vscode")
    vscode_dir.mkdir(exist_ok=True)
    config_path = vscode_dir / "mcp.json"

    # Merge into existing config if present
    if config_path.exists():
        try:
            with open(config_path) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}
    else:
        existing = {}

    servers = existing.setdefault("servers", {})
    servers["pneuma"] = entry

    with open(config_path, "w") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")

    return str(config_path.resolve())


def setup_cursor() -> str:
    """Build Cursor MCP config JSON and return it as a formatted string.

    Cursor stores config in its settings DB, so we print it for the user
    to paste into Settings → MCP Servers → Add Server.
    """
    paths = _detect_paths()
    entry = {
        "command": paths["python"],
        "args": ["-m", "mcp_server.server"],
        "cwd": paths["pneuma_root"],
    }
    if paths.get("user_project"):
        entry["env"] = {"PNEUMA_PROJECT": paths["user_project"]}
    config = {
        "mcpServers": {
            "pneuma": entry,
        }
    }
    return json.dumps(config, indent=2)


def setup_claude_code() -> str:
    """Generate or update .mcp.json in the current directory for Claude Code.

    Claude Code reads project-level MCP servers from .mcp.json at the
    project root. Returns the path written to.
    """
    paths = _detect_paths()
    entry = {
        "command": paths["python"],
        "args": ["-m", "mcp_server.server"],
        "cwd": paths["pneuma_root"],
    }
    if paths.get("user_project"):
        entry["env"] = {"PNEUMA_PROJECT": paths["user_project"]}

    config_path = Path(".mcp.json")

    if config_path.exists():
        try:
            with open(config_path) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}
    else:
        existing = {}

    existing.setdefault("mcpServers", {})["pneuma"] = entry

    with open(config_path, "w") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")

    return str(config_path.resolve())


def _scaffold_pneuma_yaml(project_path: str | None) -> None:
    """Create a .pneuma.yaml in the project directory if one doesn't exist yet."""
    target_dir = Path(project_path) if project_path else Path(".")
    target = target_dir / ".pneuma.yaml"

    if target.exists():
        print(f"  .pneuma.yaml : already exists at {target} (skipped)")
        return

    try:
        import yaml  # noqa: F401
        yaml_available = True
    except ImportError:
        yaml_available = False

    if not yaml_available:
        print("  .pneuma.yaml : skipped (PyYAML not installed — run: pip install -e .[yaml])")
        return

    content = """\
# .pneuma.yaml — miner configuration for this project
# Edit the values below, then run `pneuma config show` to verify.
# Full reference: docs/mining.md

miner:
  # ── Parallelism ────────────────────────────────────────────────────────────
  # Raise for large codebases to speed up the first mine (each worker chunks
  # and embeds one file; sentence-transformers releases the GIL, so workers
  # run in parallel on all CPU cores).
  workers: 4

  # ── File limits ────────────────────────────────────────────────────────────
  max_file_size: 100000   # bytes — skip files larger than this
  max_files: 5000         # safety cap on total files per run

  # ── Gitignore integration ──────────────────────────────────────────────────
  # When true, patterns from .gitignore are automatically treated as skip rules.
  respect_gitignore: true

  # ── Skip patterns ──────────────────────────────────────────────────────────
  # Gitignore-style globs matched against the relative file path.
  # Uncomment and extend for vendor trees, generated files, etc.
  # skip:
  #   - "third_party/**"
  #   - "vendor/**"
  #   - "**/*_generated.*"

  # ── Priority ───────────────────────────────────────────────────────────────
  # Files matching these patterns are mined first — useful so READMEs and
  # architecture docs surface early when search scores tie.
  # priority:
  #   - "README.md"
  #   - "ARCHITECTURE.md"
  #   - "docs/**"
"""

    target.write_text(content, encoding="utf-8")
    print(f"  .pneuma.yaml : created at {target.resolve()}")
    print(f"               → edit to customise skip patterns, workers, and priority")


def run_setup(ide: str) -> None:
    """Run the setup wizard for the given IDE."""
    paths = _detect_paths()

    print(f"\nDetected paths:")
    print(f"  Python  : {paths['python']}")
    print(f"  Pneuma  : {paths['pneuma_root']}")
    if paths.get("user_project"):
        print(f"  Project : {paths['user_project']}")
    else:
        print(f"  Project : not detected — run `pneuma init` first, or run this from your project dir")

    # Verify MCP server works
    if _verify_server():
        print(f"  Server  : OK (importable)")
    else:
        print(f"  Server  : FAILED — run 'pip install -e .' first")
        sys.exit(1)

    print()

    if ide == "vscode":
        written = setup_vscode()
        print(f"Wrote VS Code config to: {written}")
        print(f"Restart VS Code to activate. Your agent now has access to Pneuma's tools.")

    elif ide == "cursor":
        config_json = setup_cursor()
        print("Add this to Cursor → Settings → MCP Servers → Add Server:\n")
        print(config_json)
        print(f"\nThen restart Cursor to activate.")

    elif ide == "claude-code":
        written = setup_claude_code()
        print(f"Wrote Claude Code config to: {written}")
        print(f"Restart Claude Code (or run 'claude' again) to activate.")
        print(f"Your agent now has access to Pneuma's tools.")

    else:
        print(f"Unknown IDE: {ide}. Supported: vscode, cursor, claude-code")
        sys.exit(1)

    # Scaffold .pneuma.yaml in the project directory (skipped if already exists)
    print()
    _scaffold_pneuma_yaml(paths.get("user_project"))
