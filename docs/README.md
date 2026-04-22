# Pneuma

**Auto-Curated AI Memory for Your Codebase**

Pneuma is a zero-friction memory layer for AI coding assistants. It mines your codebase, ingests team knowledge from Slack and Microsoft Teams, and exposes everything to your IDE through the Model Context Protocol (MCP).

Your AI agent reads from the knowledge base at session start, saves decisions and solutions during work, and stays synchronized with your codebase automatically — without any manual maintenance.

---

## Quick Start

```bash
pip install -e .
cp .env.example .env          # add tokens for Slack/Teams if needed
pneuma quickstart /path/to/your/project
```

See the [Getting Started](getting-started.md) guide for full installation instructions.

---

## How It Works

```
Your codebase + team chat
         │
         ▼
    Pneuma MCP Server
    ┌────────────────────────────────┐
    │  Mine code  │  Ingest chat    │
    │  Auto-route │  Deduplicate    │
    │  Search     │  Optimize       │
    └─────────────┬──────────────────┘
                  │
                  ▼
           MemPalace (storage)
           ChromaDB + SQLite
                  │
                  ▼
     IDE (VS Code · Cursor · Claude)
```

---

## What's in These Docs

| Section | What It Covers |
|---------|---------------|
| [Getting Started](getting-started.md) | Install, configure, and run your first quickstart |
| [Configuration](configuration.md) | All environment variables and IDE config options |
| [Teams Setup](teams-setup.md) | Azure AD app registration and Graph API permissions |
| [Pneuma vs MemPalace](pneuma-vs-mempalace.md) | Architecture overview and when to use each |
| [Features](features/index.md) | Full feature guides: MCP tools, CLI, mining, diary, and more |

---

## Links

- [GitHub](https://github.com/knrl/pneuma)
- [MemPalace](https://github.com/knrl/mempalace) — the storage engine Pneuma builds on
