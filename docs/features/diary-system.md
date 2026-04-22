# Diary System

Persistent journal for AI agents and humans. Entries are timestamped, scoped per agent, topic-tagged, and bounded to avoid unbounded growth.

---

## How It Works

```
┌──────────────┐     write_diary()     ┌──────────────┐
│  AI Agent    │ ──────────────────────▶│  Palace      │
│  (Copilot)   │                        │  Diary Wing  │
│              │◀─────────────────────  │              │
└──────────────┘     read_diary()      └──────────────┘
```

Diary entries are stored in the palace using the agent's name as a scoping key. Each entry includes a timestamp, topic tag, and the entry text.

## Usage

### CLI

```bash
# Write diary entries
pneuma diary write "Migrated auth to JWT tokens today"
pneuma diary write "Fixed N+1 query in orders endpoint" -t performance
pneuma diary write "Noticed the test suite takes 4 minutes — investigate CI caching" -t observation

# Read recent entries
pneuma diary read
pneuma diary read -n 20                    # Last 20 entries
pneuma diary read -a copilot               # Read Copilot's diary
pneuma diary read -a copilot -n 5          # Last 5 Copilot entries
```

### MCP Tools (AI Agent)

**`write_diary`** — The agent records observations during a session:

```
Tool: write_diary
  entry: "Discovered that the billing module has circular imports between invoice.py and payment.py. Need to extract shared types."
  topic: "code-quality"
  agent_name: "copilot"
```

**`read_diary`** — The agent reads its journal at the start of a session:

```
Tool: read_diary
  agent_name: "copilot"
  limit: 5
```

Returns:

```
[2026-04-18 14:32] (general)
  Migrated auth to JWT tokens today

[2026-04-18 16:15] (performance)
  Fixed N+1 query in orders endpoint — was loading all line items per order

[2026-04-19 09:00] (observation)
  Noticed the test suite takes 4 minutes — investigate CI caching
```

## Use Cases

### Agent Session Continuity

An AI agent reads its diary at the start of a conversation to recall what it was doing:

```
Agent reads diary → "Last session I fixed the N+1 query in orders.
                     I also noticed the billing module has circular imports."
```

### Decision Logging

Record architectural decisions with context:

```bash
pneuma diary write "Decided to use Redis for session storage instead of PostgreSQL — sessions are ephemeral and Redis handles TTL natively" -t architecture
```

### Progress Tracking

Track work across multiple sessions:

```bash
pneuma diary write "Started refactoring payment module - extracted PaymentProcessor interface" -t refactor
pneuma diary write "Payment refactor: migrated Stripe adapter to new interface" -t refactor
pneuma diary write "Payment refactor: complete. All 47 tests passing." -t refactor
```

### Observations for Future Work

Note things that aren't urgent but should be addressed:

```bash
pneuma diary write "The error handling in webhook.py swallows exceptions silently. Should add logging." -t tech-debt
```

## Automatic Retention

Diary entries are automatically pruned to stay bounded. When a new entry is written, if the total count exceeds the retention limit (default 200), the oldest entries are deleted.

| Variable | Default | Purpose |
|---|---|---|
| `DIARY_MAX_ENTRIES` | `200` | Maximum diary entries per agent. Oldest entries beyond this limit are deleted on each write. |

At 1-3 sentences per entry, 200 entries is roughly 50KB — enough for months of session context without unbounded growth.

## Best Practice: Keep Entries Brief

To get the most out of the retention window:

- **1-3 sentences max** per entry
- Focus on **what changed**, **what was decided**, or **what to remember next time**
- Avoid verbose session summaries — capture the key fact, not the narrative

## Parameters

### Write

| Parameter | Default | Description |
|-----------|---------|-------------|
| `entry` | (required) | The diary entry text |
| `agent_name` | `"copilot"` (MCP) / `"pneuma"` (CLI) | Which agent's diary to write to |
| `topic` | `"general"` | Topic tag for the entry |

### Read

| Parameter | Default | Description |
|-----------|---------|-------------|
| `agent_name` | `"copilot"` (MCP) / `"pneuma"` (CLI) | Which agent's diary to read |
| `limit` | `5` (MCP) / `10` (CLI) | Number of recent entries to return |

## Compared to raw MemPalace

MemPalace has a diary primitive, but without Pneuma:
- No CLI for quick journal writes
- No MCP tool for AI agents to read/write diaries
- No integration with the rest of the knowledge management workflow
