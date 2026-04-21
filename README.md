<p align="center">
  <img src="docs/pneuma_logo.png" alt="Pneuma" width="180" />
</p>

<h1 align="center">Pneuma</h1>
<p align="center"><strong>Auto-Curated AI Memory for Your Codebase</strong></p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-compatible-purple.svg" alt="MCP Compatible"></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome"></a>
</p>

Pneuma gives your AI coding assistant persistent memory. It mines your codebase, ingests Slack/Teams chat, and exposes everything via MCP tools — so the assistant knows your project, not just the current file.

Built on [MemPalace](https://github.com/knrl/mempalace). Embeddings run locally. No data leaves your machine during retrieval.

---

## How It Works

```
┌──────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  IDE (Copilot /  │────▶│  Pneuma MCP Server  │────▶│  Core Engine     │
│  Cursor / Claude)│◀────│  (17 core + 4 chat) │◀────│  (MemPalace)     │
└──────────────────┘     └──────────┬──────────┘     └──────────────────┘
                                    │ chat ingestion
                                    ▼
                         ┌──────────────────────┐
                         │  Slack / Teams       │
                         └──────────────────────┘
```

---

## What It Does

- Mines your codebase on `pneuma init`, keeps it up to date with `pneuma mine`
- Ingests Slack / Teams channels on demand (noise filter, PII strip, problem/solution extraction)
- Routes content to the right part of the knowledge base automatically
- Deduplicates and prunes stale entries automatically
- Exposes 20 MCP tools to your IDE assistant and 23 CLI commands for you
- Escalates to humans when retrieval confidence is too low

---

## Quick Start

**macOS / Linux**
```bash
git clone https://github.com/knrl/pneuma.git && cd pneuma
python3 -m venv .venv && source .venv/bin/activate && pip install -e .
cp .env.example .env   # edit with your tokens
pneuma quickstart /path/to/your/project
```

**Windows (PowerShell)**
```powershell
git clone https://github.com/knrl/pneuma.git; cd pneuma
python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -e .
Copy-Item .env.example .env   # edit with your tokens
pneuma quickstart C:\path\to\your\project
```

`quickstart` scaffolds `.pneuma.yaml` (pauses so you can tune it), mines the project, auto-configures your IDE, and runs `pneuma doctor`. Restart your IDE when it finishes.

→ **[Full setup guide](docs/getting-started.md)** (Slack, Teams, VS Code, Cursor, Claude Code)

---

## First Commands

```bash
pneuma status -v              # what's in the palace
pneuma search "authentication" # semantic search
pneuma explore                # wing/room map
pneuma recent -n 10           # what was just ingested
pneuma doctor                 # verify everything is wired up
```

From your IDE, ask the assistant:
- *"what does the auth module do?"*
- *"search memory for how we handle rate limiting"*
- *"save this decision: we use JWT with 1-hour expiry"*

---

## Documentation

| Guide | Description |
|---|---|
| [Getting Started](docs/getting-started.md) | Full install — VS Code, Cursor, Claude Code, Slack, Teams |
| [CLI Reference](docs/features/04-cli-commands.md) | All 23 CLI commands |
| [MCP Tools](docs/features/03-mcp-tools.md) | Agent tool reference |
| [Slack Integration](docs/features/01-slack-integration.md) | Slack app setup and ingestion |
| [Teams Integration](docs/teams-setup.md) | Teams Azure AD app + webhook setup |
| [On-Demand Import](docs/features/02-on-demand-import.md) | Import docs, chat exports, text |
| [Codebase Mining](docs/mining.md) | How init/mine work, config, incremental mode |
| [All Feature Guides](docs/features/README.md) | Full index |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
