# Slack Integration & Auto-Ingestion

On-demand Slack channel ingestion: fetches messages, filters noise, strips PII, and extracts problem/solution pairs into the knowledge base.

---

## How It Works

Pneuma does **not** require a separate background daemon or worker process. Instead, Slack ingestion is triggered on-demand — the `ingest_chat_channel` MCP tool (with `platform="slack"`) fetches and ingests channel history when called.

```
┌──────────────┐  periodic trigger  ┌──────────────┐
│  Scheduler   │ ──────────────────▶│  Pneuma MCP  │
│  (your app)  │                    │  Server      │
└──────────────┘                    └──────┬───────┘
                                           │
                                   ingest_chat_channel
                                   (platform="slack")
                                           │
                                    ┌──────▼───────┐
                                    │  Preprocessing│
                                    │  Pipeline     │
                                    └──────┬───────┘
                                           │
                                    ┌──────▼───────┐
                                    │  Knowledge   │
                                    │  Base        │
                                    └──────────────┘
```

When `ingest_chat_channel` is called with `platform="slack"`, it fetches recent messages and runs them through the preprocessing pipeline:

```
Buffer → Noise Filter → Anonymizer → Story Extractor → Knowledge Base
```

**Noise Filter** — Embedding similarity classifier (with structural fast-path rules) that separates signal from noise:

| Dropped (noise) | Kept (signal) |
|------------------|---------------|
| "good morning!" | "Bug: auth tokens expire after 5 min" |
| "lol 😂" | "Fixed: add retry logic to the webhook handler" |
| "anyone want pizza?" | "We decided to use JWT instead of session cookies" |
| "👍" | "Workaround: set `MAX_RETRIES=3` in .env" |
| "brb" | "How do we handle rate limiting on the /api/v2 endpoint?" |

**Anonymizer** — Strips PII before storage:
- `<@U1234ABC>` → `User-1` (stable pseudonyms per extraction cycle)
- `john@company.com` → `[REDACTED]`
- `192.168.1.100` → `[REDACTED]`
- Phone numbers → `[REDACTED]`

**Story Extractor** — Converts filtered messages into structured Problem/Solution pairs using a question→answer heuristic. Messages containing a question mark (`?`) become Problems; subsequent non-question messages become Solutions.

### Optimization

After ingestion, you can run `optimize_memory` (MCP tool) or `pneuma optimize` (CLI) to keep the knowledge base clean:
- Merges near-duplicates (cosine similarity > 0.92)
- Deletes stale entries (> 180 days old)
- Scans index health and checks for contradictions

## Setup

### 1. Create a Slack App

Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app. Socket Mode and Event Subscriptions are **not required** — Pneuma fetches Slack history on demand via the API, not through incoming webhooks or push events.

### 2. Configure OAuth Scopes

Add these **Bot Token Scopes**:

| Scope | Purpose |
|-------|---------|
| `channels:history` | Read public channel messages |
| `channels:read` | List channels for channel name resolution |
| `chat:write` | Post messages (for `ask_team` and escalation) |

Add this **User Token Scope** (for `check_recent_chat`):

| Scope | Purpose |
|-------|--------|
| `search:read` | Search workspace messages (user-token-only API) |

> **Note:** Slack's `search.messages` API requires a user token (`xoxp-...`). Without it, all other tools work fine — only `check_recent_chat` will be unavailable.

### 3. Configure Environment

```bash
# .env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_USER_TOKEN=xoxp-your-user-token     # For check_recent_chat (search.messages)
ALLOWED_CHANNELS=C01ABC123,C02DEF456
ESCALATION_CHANNEL=C03GHI789
SLACK_DEFAULT_CHANNEL=C01ABC123
```

### 4. Use Slack MCP Tools

No additional service or process required. Your AI agent interacts with Slack directly through MCP tools:

| Tool | What It Does |
|------|-------------|
| `check_recent_chat(topic, platform="auto")` | Search recent messages for a topic |
| `ask_team(question, target="", platform="auto")` | Post a question to a channel |
| `ingest_chat_channel(channel, platform="slack", ...)` | On-demand backfill |
| `escalate_to_human(question, code_context, platform="auto")` | Route unanswerable questions |

These tools work with both Slack and Teams — `platform="auto"` picks whichever is configured. To force Slack, pass `platform="slack"`.

## Compared to raw MemPalace

MemPalace is a storage engine — it doesn't know about Slack. Without Pneuma:
- You'd need to manually copy team conversations into the palace
- There's no noise filtering or PII anonymization
- No automatic Problem/Solution structuring
- No MCP tools for on-demand channel ingestion
