# Pneuma vs MemPalace

> TL;DR — MemPalace is the engine. Pneuma is the automation layer that drives it.

---

## What each one is

**MemPalace** is a structured memory storage system. It gives you:
- A spatial hierarchy (wings → rooms → drawers)
- Local vector embeddings via sentence-transformers
- A temporal knowledge graph (SQLite)
- A diary system
- Semantic search
- An MCP server for direct IDE access

It does none of this automatically. You decide what to save, how to organise it, when to mine, and when to clean up. It is a powerful tool that rewards disciplined use.

**Pneuma** is an automation and integration layer built on top of MemPalace. It uses MemPalace as its storage engine and adds everything around it: automated ingestion, routing, team chat integration, confidence scoring, and a purpose-built MCP tool surface for AI coding assistants.

---

## Feature comparison

| | MemPalace | Pneuma |
|---|---|---|
| **Storage engine** | ✅ Is the engine | ✅ Uses MemPalace |
| **Codebase mining** | ✅ `mempalace mine` | ✅ `pneuma init` + `pneuma mine` |
| **Room structure** | Directory-mirroring | Directory-mirroring + canonical rooms (`tests`, `docs`) + depth-2 expansion for large dirs |
| **Chunking** | Whole-file (default) | Symbol-level via tree-sitter (or char-based fallback) |
| **File summaries** | ❌ | ✅ One summary entry per file for broad queries |
| **Incremental mining** | ❌ | ✅ SQLite state — only re-embed changed files |
| **Setup** | Interactive (entity confirmation, room review) | Fully automated — one command |
| **Team chat ingestion** | ❌ None | ✅ Slack + Microsoft Teams |
| **Noise filtering** | ❌ None | ✅ Rule-based, discards chatter |
| **PII anonymization** | ❌ None | ✅ Strips mentions, emails, IPs before storage |
| **Auto-routing** | ❌ Manual wing/room choice | ✅ Keyword classifier routes automatically |
| **Deduplication** | `mempalace dedup` (manual CLI) | ✅ Uses MemPalace batch dedup + auto-schedules every 50 writes or 7 days |
| **Stale cleanup** | ❌ None | ✅ Age-based (180 days), auto-scheduled |
| **Index health** | `mempalace repair` (manual CLI) | ✅ Auto-scans on every optimize; rebuild via `--level deep` |
| **Fact checking** | `mempalace.fact_checker` (library) | ✅ Samples entries automatically on every optimize |
| **Multi-project isolation** | Config files in each project | Isolated palaces in `~/.pneuma/palaces/` |
| **Knowledge graph** | ✅ Temporal SQLite-backed | ✅ Wraps MemPalace KG with CLI + MCP tools |
| **CLI** | `mempalace` commands | `pneuma` commands (init, status, search, explore…) |

---

## Room structure

Pneuma uses two fixed wings: `code` (mirrors your directory structure) and `chat` (team knowledge from Slack/Teams + keyword routing).

```
wing: code
  rooms: src, tests, docs, scripts,
         config, migrations, assets, general

wing: chat
  rooms: decisions, conventions, solutions,
         workarounds, escalations, context
```

Three routing rules apply on top of plain mirroring:

1. **Canonical rooms** — `tests/`, `test/`, `spec/` always map to room `tests`; `docs/`, `doc/` always map to `docs`, regardless of project.
2. **Depth-2 expansion** — if a top-level directory has ≥ 5 immediate subdirectories (configurable via `miner.depth2_threshold`), files inside it are routed to `top-sub` rooms (e.g. `iclbase/authorization/` → room `iclbase-authorization`).
3. **Root-level files** — files sitting directly at the project root go to room `general`.

See [Codebase Mining](features/mining.md) for full details.

---

## Knowledge sources

| Source | MemPalace | Pneuma |
|---|---|---|
| Your code files | ✅ `mempalace mine` | ✅ `pneuma init` |
| Manual notes | ✅ `mempalace add` | ✅ `pneuma import --text` |
| Documents (markdown, txt) | ✅ | ✅ `pneuma import` |
| Slack conversations | ❌ | ✅ `ingest_chat_channel(platform="slack")` |
| Microsoft Teams conversations | ❌ | ✅ `ingest_chat_channel(platform="teams")` |
| Slack JSON exports | ❌ | ✅ `pneuma import --type chat-history` |
| Agent diary (session reflections) | ✅ | ✅ |

---

## When to use each

**Use MemPalace directly if:**
- You want full control over every memory entry
- You work alone and maintain your palace manually
- You need directory-accurate rooms for precise scoping
- You don't use Slack or Teams
- You want the engine without the automation overhead

**Use Pneuma if:**
- You want zero ongoing maintenance
- Your team produces knowledge in Slack or Teams that gets lost
- You want AI-assisted coding with institutional memory built in
- You're setting up memory for a team, not just yourself

**Use both together:**
MemPalace's `mempalace mine` creates directory-accurate rooms. Pneuma then layers chat knowledge, auto-routing, and MCP tools on top of the same palace. This is the most powerful setup but requires manual coordination (they use separate palace paths by default).

---

## Maintenance burden

| Task | MemPalace | Pneuma |
|---|---|---|
| Add new knowledge | Manual — you write/paste it | Automatic from chat; manual via `save_knowledge` MCP |
| Remove duplicates | Manual | Automatic (every 50 writes or 7 days); `pneuma optimize` for manual override |
| Archive stale entries | Manual | Automatic after 180 days (configurable) |
| Re-mine after code changes | `mempalace mine .` | Automatic on session start (`wake_up`); `pneuma mine` for manual override |
| Organise into wings/rooms | Interactive at init, manual thereafter | Auto-routing on every save |

---

## Token consumption (quick reference)

Token counts shown are approximate averages measured on representative projects.

| Approach | Tokens per query (top_k=5) |
|---|---|
| Pneuma, tree-sitter chunks + summaries | ~1 500 |
| Pneuma, char-fallback chunks + summaries | ~2 150 |
| Whole-file (avg 3 500 chars) | ~5 000 |
| Whole-file (large files, 15 000 chars) | ~21 500 |

---

## The relationship in one diagram

```
                    ┌─────────────────────────────┐
                    │           Pneuma             │
                    │                              │
                    │  Slack / Teams ingestion     │
                    │  Auto-routing                │
                    │  20+ MCP tools               │
                    │  Confidence + escalation     │
                    │  Dedup + stale cleanup       │
                    │  Codebase miner              │
                    └─────────────┬───────────────┘
                                  │ uses
                    ┌─────────────▼───────────────┐
                    │         MemPalace            │
                    │                              │
                    │  Wings / rooms / drawers     │
                    │  Local vector embeddings     │
                    │  Temporal knowledge graph    │
                    │  Diary                       │
                    │  ChromaDB + SQLite           │
                    └─────────────────────────────┘
```

Pneuma does not replace MemPalace. It removes the friction of using it.
