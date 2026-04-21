# MCP Tools — AI Agent Integration

Pneuma exposes **17 core tools + 4 conditional chat tools** via the Model Context Protocol. The chat tools are platform-agnostic — one tool per operation that works with both Slack and Microsoft Teams. They register when either `SLACK_BOT_TOKEN` or `TEAMS_CLIENT_ID` is set.

---

## How It Works

Pneuma runs a FastMCP server over `stdio` transport. When configured in your IDE, the AI agent automatically discovers and uses these tools during conversations.

```
┌──────────────────────┐         ┌──────────────────┐
│  IDE                 │  stdio  │  Pneuma MCP      │
│  (Copilot / Cursor / │◀───────▶│  Server           │
│   Claude Code /      │         │  (17 core + 4     │
│   Claude Desktop)    │         │   chat conditional)│
└──────────────────────┘         └────────┬─────────┘
                                          │
                                          ▼
                                 ┌──────────────────┐
                                 │  core/palace.py   │
                                 │  (adapter)        │
                                 └────────┬─────────┘
                                          │
                                 ┌────────▼─────────┐
                                 │  MemPalace +      │
                                 │  Knowledge Graph   │
                                 └──────────────────┘
```

**Recommended usage flow:**
- Session start: `wake_up` → `recall` (if needed)
- User question: `search_memory` → answer (or `escalate_to_human`)
- New knowledge: `save_knowledge` (auto-dedup, auto-route)
- Reflection: `write_diary`

## Tool Categories

### Memory Tools (9)

Core knowledge operations — search, store, mine, and maintain.

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `wake_up` | `wing=""` | Load identity + essential context (~800 tokens). Call once at session start |
| `recall` | `wing=""`, `room=""`, `n_results=10` | On-demand retrieval from a specific wing/room |
| `search_memory` | `query`, `top_k=5`, `group_by_location=False` | Semantic search with confidence scores; group by location to explore cross-domain connections |
| `save_knowledge` | `content`, `wing=""`, `room=""`, `tags=""`, `source=""` | Store with auto-routing and auto-dedup; returns routing feedback |
| `palace_overview` | `detail="summary"` | Palace stats; pass `detail="full"` for complete taxonomy + graph connectivity |
| `mine_codebase` | `project_path=""`, `dry_run=False`, `full=False` | Walk the project and embed source files. Runs automatically in the background on `wake_up`; call explicitly with `full=True` to force a complete re-mine or `dry_run=True` to preview. Skip patterns, generated-file rules, and priority order are configured via `.pneuma.yaml` at the project root — see [Codebase Mining](../mining.md) |
| `optimize_memory` | `dry_run=False`, `level="standard"` | Multi-stage optimization: dedup, stale cleanup, index health, fact check, indexing status. Pass `level="deep"` for compression, rebuild, migration (forced to dry-run via MCP — use CLI for actual deep runs). Auto-triggers every 50 writes or 7 days |
| `delete_entry` | `entry_id` | Delete a specific entry by ID |
| `initialize_project` | `identity=""` | One-time post-quickstart setup. Call with no args first to get a palace overview, then call again with a project identity description to write `~/.mempalace/identity.txt`. `wake_up` hints to call this when no identity is configured |

### Knowledge Graph Tools (3)

Track temporal facts and relationships between entities.

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `track_fact` | `subject`, `predicate`, `value`, `valid_from=""`, `confidence=1.0` | Record a relationship: `auth-service → uses → JWT` |
| `query_facts` | `entity`, `as_of=""`, `direction="both"`, `chronological=False` | Look up entity relationships; `chronological=True` for timeline view |
| `invalidate_fact` | `subject`, `predicate`, `value`, `ended=""` | Mark a fact as no longer true (preserves history) |

> KG summary stats (entity count, fact counts, relationship types) are available via `palace_overview(detail="full")` — no separate tool.

### Navigation Tools (2)

Explore the palace structure and discover cross-wing connections.

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `explore_palace` | `start_room`, `max_hops=2` | Walk the palace graph from a room, discovering neighbors |
| `find_bridges` | `wing_a=""`, `wing_b=""` | Find rooms that bridge multiple wings |

### Diary Tools (2)

Personal journals for AI agents — track observations, decisions, and context across sessions.

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `write_diary` | `entry`, `topic="general"`, `agent_name="copilot"` | Write a timestamped journal entry |
| `read_diary` | `agent_name="copilot"`, `limit=5` | Read recent diary entries |

### Chat Tools (4) — platform-agnostic, conditional

These tools work with **both Slack and Microsoft Teams**. Each accepts an
optional `platform` parameter (`"slack"`, `"teams"`, or `"auto"`). When set
to `"auto"` (default), Pneuma uses whichever backend is configured — Slack
is preferred when both are available.

These tools register when **either** `SLACK_BOT_TOKEN` **or** `TEAMS_CLIENT_ID`
is set. Under the hood, they delegate to the platform-specific modules
(`chat_tools`, `slack_ingest_tools`, `teams_chat_tools`, `teams_ingest_tools`,
`escalation`) — but the agent never sees that split.

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `check_recent_chat` | `topic`, `count=10`, `platform="auto"` | Search recent chat messages for a topic |
| `ask_team` | `question`, `target=""`, `platform="auto"` | Post a question; `target` is channel ID (Slack) or webhook URL (Teams) |
| `ingest_chat_channel` | `channel`, `platform`, `hours_back=24.0`, `limit=200`, `team_id=""` | Fetch and ingest channel history. `platform` is **required** (channel ID formats differ) |
| `escalate_to_human` | `question`, `code_context`, `platform="auto"` | Post an escalation with code context to the team |

**Why unified?** Before consolidation, the agent saw 8 tools — 4 Slack + 4 Teams doing the same things. Platform is an implementation detail; the agent shouldn't care. If your team switches Slack → Teams, nothing in your IDE config or agent prompt changes.

### Import Tools (1)

Import documents and text directly through the AI agent.

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `import_content` | `file_path=""`, `content=""`, `doc_type="auto"`, `title=""`, `wing=""`, `room=""` | Import a file or pasted text (auto-detects format, PII-anonymizes chat content) |

### Prompts (reference material)

| Prompt | Purpose |
|--------|---------|
| `memory_dialect` | AAAK compressed memory specification (reference, not an action) |
| `capture_guidelines` | Decision matrix for when to call `import_content` autonomously — loaded automatically via the `wake_up` hint |

## IDE Setup

The easiest way to configure your IDE is with the setup command:

```bash
pneuma setup vscode       # Creates/merges .vscode/mcp.json
pneuma setup cursor       # Prints JSON for Cursor settings
pneuma setup claude-code  # Creates/merges .mcp.json at project root
```

This auto-detects your Python path and project root. Reference config templates are also available in `mcp_server/config/`.

<details>
<summary>Manual config (if you prefer not to use <code>pneuma setup</code>)</summary>

### VS Code (GitHub Copilot)

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "pneuma": {
      "type": "stdio",
      "command": "/absolute/path/to/pneuma/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/pneuma"
    }
  }
}
```

### Cursor

Add to Cursor Settings → MCP Servers:

```json
{
  "mcpServers": {
    "pneuma": {
      "command": "/absolute/path/to/pneuma/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/pneuma"
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pneuma": {
      "command": "/absolute/path/to/pneuma/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/pneuma"
    }
  }
}
```

> Replace `/absolute/path/to/pneuma` with the actual path where you cloned the repo.

</details>

## Compared to raw MemPalace

MemPalace is a Python library — it has no MCP server, no tool definitions, no IDE integration. Without Pneuma:
- Your AI agent cannot access the knowledge base
- No tool abstractions (search, save, explore, etc.)
- No content classification or auto-routing
- No escalation workflow
- No Slack integration from the agent
