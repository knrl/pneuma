# Pneuma — Feature Guides

Pneuma adds automation and IDE integration on top of [MemPalace](https://github.com/knrl/mempalace). Each feature guide below explains what a capability does, how it works, and how to use it.

New here? Start with the [Getting Started guide](../getting-started.md).

---

## Feature Guides

| # | Feature | What It Does |
|---|---------|-------------|
| 01 | [Slack Integration](01-slack-integration.md) | On-demand channel ingestion: noise filter, PII anonymization, problem/solution extraction |
| 02 | [On-Demand Import](02-on-demand-import.md) | Import decision docs, chat exports, and text into the knowledge base |
| 03 | [MCP Tools](03-mcp-tools.md) | 17 core + 4 platform-agnostic chat tools for AI coding assistants via Model Context Protocol |
| 04 | [CLI Commands](04-cli-commands.md) | 23 commands for humans to manage and query the knowledge base |
| 05 | [Optimization Engine](05-refactor-engine.md) | 9-stage pipeline: batch dedup, stale cleanup, index health, fact check, compression, rebuild, migration |
| 06 | [Diary System](06-diary-system.md) | Persistent journals for agents and humans across sessions |
| 07 | [Wake-Up & Recall](07-wakeup-recall.md) | Load project context at session start for AI agents |
| 08 | [Palace Navigation](08-palace-navigation.md) | Graph traversal and cross-wing connection discovery |
| 09 | [Knowledge Graph](09-knowledge-graph.md) | Temporal fact tracking with time-travel queries |
| 10 | [Auto-Categorization](10-auto-categorization.md) | Automatic content routing to the right wing/room |

---

## Other Docs

| Doc | Description |
|---|---|
| [Getting Started](../getting-started.md) | Full installation and setup |
| [Configuration](../configuration.md) | All environment variables and IDE config |
| [Technical Reference](../Technical_Documentation.md) | Architecture, data flow, module reference |
| [Security Checklist](../security_audit_checklist.md) | Security audit checklist |

---

## The Stack

```
┌─────────────────────────────────────────────┐
│  Pneuma (this project)                      │
│                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
  │ CLI (23  │  │ MCP (20  │  │ Slack /  │ │
│  │ commands)│  │ tools)   │  │ Teams    │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │              │              │       │
│  ┌────▼──────────────▼──────────────▼────┐ │
│  │         Core Engine                    │ │
│  │  Auto-Init · Router · Refactor ·      │ │
│  │  Ingestion · RAG · Confidence         │ │
│  └────────────────┬──────────────────────┘ │
│                   │                         │
│  ┌────────────────▼──────────────────────┐ │
│  │         palace.py (adapter)            │ │
│  └────────────────┬──────────────────────┘ │
└───────────────────┼─────────────────────────┘
                    │
         ┌──────────▼──────────┐
         │   MemPalace (pip)   │
         │   ChromaDB + SQLite │
         └─────────────────────┘
```
