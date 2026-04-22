# Palace Exploration & Navigation

CLI and MCP tools to explore the palace structure, walk room-to-room connections, and find rooms that bridge multiple wings.

---

## The Palace as a Graph

Pneuma models the palace as a connected graph:

```
                    ┌──────────────┐
           ┌───────│ code/src     │───────┐
           │       └──────────────┘       │
           │                              │
    ┌──────▼───────┐             ┌───────▼─────────┐
    │ code/config  │             │ chat/decisions   │
    └──────┬───────┘             └───────┬─────────┘
           │                              │
    ┌──────▼──────────────┐     ┌────────▼────────┐
    │ chat/solutions      │─────│ chat/escalations │
    └─────────────────────┘     └─────────────────┘
```

Rooms that belong to multiple wings (or share entries with cross-references) become **tunnels** — bridges connecting different domains.

## Navigation Tools

### `explore_palace` — Walk the Graph

Start from a room and discover what's nearby, up to N hops away.

```
Tool: explore_palace
  start_room: "src"
  max_hops: 2
```

Returns:

```
Starting from: src

Hop 1:
  tests (code) — 12 entries
  decisions (chat) — 8 entries

Hop 2:
  solutions (chat) — 23 entries
  docs (code) — 45 entries
```

### `find_bridges` — Discover Cross-Wing Bridges

Find rooms that connect different wings.

```
Tool: find_bridges
  wing_a: "code"
  wing_b: "chat"
```

Returns:

```
Bridging rooms between code ↔ chat:
  decisions — appears in both wings, 8 entries
  src — connected to both via shared entities
```

Without wing filters, shows all tunnel rooms in the palace.

## CLI Access

### Timeline View

The `timeline` command provides a chronological navigation of knowledge graph facts:

```bash
$ pneuma timeline
2026-01-15 auth-service → uses → session-cookies [EXPIRED 2026-03-01]
2026-03-01 auth-service → uses → JWT
2026-03-15 billing-api → depends-on → stripe-sdk
2026-04-01 user-service → migrated-to → PostgreSQL

$ pneuma timeline "auth-service"
# Only facts about auth-service
```

### Status Overview

```bash
$ pneuma status
Project     : /home/dev/myapp
Palace path : ~/.pneuma/palaces/myapp/palace

Wings (2):
  code  → 3188 entries
  chat  →  186 entries
```

For a richer CLI view, use `pneuma explore` to see the full palace map or walk connections from a room, and `pneuma bridges` to find cross-wing connections without opening the MCP layer.

### Search with Grouping (MCP)

The AI agent can use `search_memory` with location grouping to find related entries:

```
Tool: search_memory
  query: "authentication"
  group_by_location: true
  n_results: 10
```

Returns entries from across all wings that relate to authentication — grouped by wing/room to show how knowledge connects across domains.

## Use Cases

### Onboarding

A new team member's AI agent explores the palace to understand the project:

```
1. palace_overview(detail="full") → "12 rooms, 342 entries across 4 wings"
2. explore_palace("src", max_hops=2) → discovers related rooms
3. find_bridges("code", "chat") → understands which code has ADRs
```

### Impact Analysis

Before making a change, the agent checks what's connected:

```
1. search_memory("payment processing") → finds relevant entries
2. explore_palace("migrations") → discovers connected rooms
3. find_bridges("code", "chat") → finds cross-wing links
4. Agent: "Changing the payment schema may affect the billing API and violate ADR-12"
```

### Knowledge Gaps

Identify areas lacking documentation:

```
palace_overview(detail="full") → "chat/escalations has 0 entries — questions are being raised but not documented"
```

## Compared to raw MemPalace

MemPalace stores entries in a hierarchy but doesn't provide graph-walking tools:
- No room-to-room hop traversal
- No cross-wing bridge discovery
- No graph statistics
- No CLI commands for navigation
- No MCP tools for AI agents to explore the structure
