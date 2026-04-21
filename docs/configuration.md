# Configuration Reference

Configuration is loaded from a `.env` file in the **Pneuma install directory** (the directory where Pneuma is installed, not your project). Copy `.env.example` there to get started:

```bash
cp /path/to/pneuma/.env.example /path/to/pneuma/.env
# then edit .env with your tokens
```

The file is loaded once at process start by `core/env.py` — there is no need to set these variables in your shell or in your project's own `.env`.

---

## Environment Variables

### Core

| Variable | Description | Default |
|---|---|---|
| `PNEUMA_PROJECT` | Path to the project being served (set by IDE config or `pneuma setup`) | — |
| `CONFIDENCE_THRESHOLD` | Retrieval score below which queries trigger escalation | `0.65` |

### Optimization

| Variable | Description | Default |
|---|---|---|
| `REFACTOR_SIMILARITY_THRESHOLD` | Cosine similarity threshold for deduplication | `0.92` |
| `REFACTOR_STALE_DAYS` | Days before an entry is considered stale | `180` |

### Slack

| Variable | Description |
|---|---|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_USER_TOKEN` | User OAuth Token (`xoxp-...`) — for `check_recent_chat` |
| `SLACK_APP_TOKEN` | App-Level Token for Socket Mode (`xapp-...`) |
| `SLACK_SIGNING_SECRET` | Signing secret for request verification |
| `ALLOWED_CHANNELS` | Comma-separated channel IDs the bot may read |
| `ESCALATION_CHANNEL` | Channel ID for escalation messages |
| `SLACK_DEFAULT_CHANNEL` | Default channel for `ask_team` tool |

> Slack tools only register when `SLACK_BOT_TOKEN` is set. All non-chat features work without it.

### Microsoft Teams

| Variable | Description |
|---|---|
| `TEAMS_CLIENT_ID` | Azure AD app (client) ID |
| `TEAMS_CLIENT_SECRET` | Azure AD app client secret |
| `TEAMS_TENANT_ID` | Azure AD tenant (directory) ID |
| `TEAMS_TEAM_ID` | Default team ID for ingestion and search |
| `TEAMS_ALLOWED_CHANNEL_IDS` | Comma-separated channel IDs the app may read |
| `TEAMS_DEFAULT_WEBHOOK_URL` | Incoming webhook URL for `ask_team` (Teams backend) |
| `TEAMS_ESCALATION_WEBHOOK_URL` | Incoming webhook URL for `escalate_to_human` (Teams backend) |

> Teams tools only register when `TEAMS_CLIENT_ID` is set. Posting tools additionally require a webhook URL.
> See [Teams Setup](teams-setup.md) for Azure AD app registration steps.

---

## Finding Slack Channel IDs

Channel IDs are required for `ALLOWED_CHANNELS`, `ESCALATION_CHANNEL`, and `SLACK_DEFAULT_CHANNEL`.

**Option 1 — Slack UI:** Right-click a channel → View channel details → scroll to the bottom.

**Option 2 — Utility script:**

```bash
python scripts/get_channel_id.py
```

---

## IDE Config Reference

### VS Code — `.vscode/mcp.json`

```json
{
  "servers": {
    "pneuma": {
      "type": "stdio",
      "command": "/absolute/path/to/pneuma/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/pneuma",
      "env": {
        "PNEUMA_PROJECT": "/absolute/path/to/your/project"
      }
    }
  }
}
```

### Cursor — Settings → MCP Servers → Add Server

```json
{
  "command": "/absolute/path/to/pneuma/.venv/bin/python",
  "args": ["-m", "mcp_server.server"],
  "cwd": "/absolute/path/to/pneuma",
  "env": {
    "PNEUMA_PROJECT": "/absolute/path/to/your/project"
  }
}
```

### Claude Desktop

macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`  
Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "pneuma": {
      "command": "/absolute/path/to/pneuma/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/pneuma",
      "env": {
        "PNEUMA_PROJECT": "/absolute/path/to/your/project"
      }
    }
  }
}
```

Template files are also available in [`mcp_server/config/`](../mcp_server/config/).

---

### Claude Code — `.mcp.json` (project root)

```json
{
  "mcpServers": {
    "pneuma": {
      "command": "/absolute/path/to/pneuma/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/pneuma",
      "env": {
        "PNEUMA_PROJECT": "/absolute/path/to/your/project"
      }
    }
  }
}
```

---

## Auto-Setup

Rather than editing config files manually, run:

```bash
cd /path/to/your/project
pneuma setup vscode       # creates/merges .vscode/mcp.json
pneuma setup cursor       # prints JSON to paste into Cursor settings
pneuma setup claude-code  # creates/merges .mcp.json
```
