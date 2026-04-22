"""
Pneuma v1.0 — Unified MCP Server.
Exposes 17 core tools + 4 conditional chat tools to AI coding assistants.

Recommended usage flow:
  Session start : wake_up → recall (if needed)
  User question : search_memory → answer (or escalate_to_human)
  New knowledge : save_knowledge (auto-dedup, auto-route)
  Reflection    : write_diary

Tool surface (21 tools):
  Memory (9)       : wake_up, recall, search_memory, save_knowledge,
                     palace_overview, mine_codebase, optimize_memory,
                     delete_entry, initialize_project
  KG (3)           : track_fact, query_facts, invalidate_fact
                     (KG stats available via palace_overview(detail="full"))
  Navigation (2)   : explore_palace, find_bridges
  Diary (2)        : write_diary, read_diary
  Chat (4)         : check_recent_chat, ask_team, ingest_chat_channel,
                     escalate_to_human
                     [registered if SLACK_BOT_TOKEN or TEAMS_CLIENT_ID set;
                      each tool takes platform="slack|teams|auto"]
  Import (1)       : import_content
"""

import logging
import os
import sys
from pathlib import Path
from mcp.server.fastmcp import FastMCP
import core.env  # noqa: F401 — loads .env from Pneuma install root

# ── Logging ──────────────────────────────────────────────────────
# MCP uses stdout for protocol framing, so we must never print to stdout.
# Route logs to ~/.pneuma/mcp-server.log so `pneuma logs` can tail them.
def _setup_logging() -> None:
    log_dir = Path(os.environ.get("PNEUMA_HOME", os.path.expanduser("~/.pneuma")))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return  # Can't write logs — silently continue
    log_path = log_dir / "mcp-server.log"

    handler = logging.FileHandler(str(log_path), encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    # Avoid duplicate handlers if main() is called repeatedly in tests
    if not any(getattr(h, "baseFilename", None) == str(log_path) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(os.environ.get("PNEUMA_LOG_LEVEL", "INFO").upper())

    # Uncaught exceptions should land in the log (MCP protocol swallows stdout)
    def _excepthook(exc_type, exc_value, exc_tb):
        logging.exception("Uncaught MCP exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.excepthook = _excepthook


_setup_logging()
_log = logging.getLogger("pneuma.mcp")
_log.info("MCP server starting (pid=%s)", os.getpid())

# ── Configure project-specific palace ────────────────────────────
# PNEUMA_PROJECT env var tells the server which project to serve.
# Set by `pneuma setup vscode/cursor` in the MCP client config.
_project_path = os.environ.get("PNEUMA_PROJECT")
if _project_path:
    from core.palace import configure
    configure(_project_path)

mcp = FastMCP(
    name="pneuma",
    instructions=(
        "You have access to Pneuma — a persistent memory and knowledge system for this project.\n\n"
        "**Start every session** by calling `wake_up()` before answering any question. "
        "This loads your agent identity and essential project context (~800 tokens).\n\n"
        "**Use Pneuma tools proactively throughout the conversation:**\n"
        "- `search_memory(query)` — before answering questions about architecture, past decisions, or technical history\n"
        "- `save_knowledge(content)` — when the user shares a decision, constraint, or important fact\n"
        "- `recall(wing, room)` — when you need deeper context on a specific area mid-conversation\n"
        "- `write_diary(entry)` — at end of sessions to record what was worked on\n\n"
        "Don't wait to be asked. The memory system only helps if you use it."
    ),
)

# ── Memory tools (9) ────────────────────────────────────────────────
from mcp_server.tools.memory_tools import (
    wake_up,
    recall,
    search_memory,
    save_knowledge,
    palace_overview,
    mine_codebase,
    optimize_memory,
    delete_entry,
    initialize_project,
)

mcp.tool()(wake_up)
mcp.tool()(recall)
mcp.tool()(search_memory)
mcp.tool()(save_knowledge)
mcp.tool()(palace_overview)
mcp.tool()(mine_codebase)
mcp.tool()(optimize_memory)
mcp.tool()(delete_entry)
mcp.tool()(initialize_project)

# ── AAAK dialect as a prompt (reference material, not an action) ─
from core.palace import aaak_spec as _aaak


@mcp.prompt()
def memory_dialect() -> str:
    """The AAAK compressed memory specification used by MemPalace."""
    result = _aaak()
    return result.get("aaak_spec", "AAAK spec not available.")


# ── Capture guidelines prompt ─────────────────────────────────────
@mcp.prompt()
def capture_guidelines() -> str:
    """When and how to proactively capture knowledge using import_content."""
    return """# Pneuma — Autonomous Capture Guidelines

You have an `import_content` tool. Use it proactively whenever the conversation
contains knowledge worth keeping — without waiting to be asked.

## When to capture immediately (call import_content now)

| Pattern | doc_type | Example |
|---------|----------|---------|
| Decision with rationale | "decision" | "We chose PostgreSQL because of JSONB support" |
| Architecture choice | "decision" | "Auth service will use JWT with 1-hour expiry" |
| Discovered constraint | "general" | "The billing API rate-limits to 100 req/min" |
| Workaround or fix | "general" | "Set MAX_RETRIES=3 to avoid the flaky webhook" |
| Pasted chat/meeting notes | "chat-history" | Slack/Teams export, meeting transcript |
| Pasted markdown document | "auto" | ADR, postmortem, runbook |

## When to use save_knowledge instead

`save_knowledge` is lighter weight — use it for short, self-contained facts
that don't need section splitting or PII anonymization:
- "We use Redis for session storage"
- "The staging database is postgres-staging.internal"

## When NOT to capture

- Code snippets the user is showing you temporarily for review
- Errors or stack traces that are being actively debugged
- Questions or hypotheticals that haven't been decided yet
- Anything the user explicitly says is temporary or scratch

## How to call import_content for pasted text

```
import_content(
    content="<the pasted text>",
    doc_type="decision",   # or "general", "chat-history", "auto"
    title="<short label>", # optional but helpful
)
```

Leave wing and room empty — auto-routing will place it correctly.

## Confirm to the user

After capturing, always tell the user what was stored and where it was routed.
Example: "Saved as a decision — routed to chat/decisions."
"""


# ── Knowledge Graph tools (3) ────────────────────────────────────
# (knowledge_stats was folded into palace_overview(detail="full"))
from mcp_server.tools.kg_tools import (
    track_fact,
    query_facts,
    invalidate_fact,
)

mcp.tool()(track_fact)
mcp.tool()(query_facts)
mcp.tool()(invalidate_fact)

# ── Navigation tools (2) ─────────────────────────────────────────
from mcp_server.tools.nav_tools import (
    explore_palace,
    find_bridges,
)

mcp.tool()(explore_palace)
mcp.tool()(find_bridges)

# ── Diary tools (2) ──────────────────────────────────────────────
from mcp_server.tools.diary_tools import (
    write_diary,
    read_diary,
)

mcp.tool()(write_diary)
mcp.tool()(read_diary)

# ── Chat tools (4) — platform-agnostic, registered if Slack OR Teams configured ─
_slack_configured = bool(os.getenv("SLACK_BOT_TOKEN", ""))
_teams_configured = bool(os.getenv("TEAMS_CLIENT_ID", ""))

if _slack_configured or _teams_configured:
    from mcp_server.tools.chat_unified import (
        check_recent_chat,
        ask_team,
        ingest_chat_channel,
        escalate_to_human,
    )

    mcp.tool()(check_recent_chat)
    mcp.tool()(ask_team)
    mcp.tool()(ingest_chat_channel)
    mcp.tool()(escalate_to_human)

# ── Import tools (1) ─────────────────────────────────────────────
from mcp_server.tools.import_tools import import_content

mcp.tool()(import_content)


def main():
    """Entry point for the MCP server."""
    _log.info(
        "Tools registered — slack=%s teams=%s project=%s",
        _slack_configured, _teams_configured, _project_path or "(not set)",
    )
    try:
        mcp.run(transport="stdio")
    except Exception:
        _log.exception("MCP server crashed")
        raise


if __name__ == "__main__":
    main()
