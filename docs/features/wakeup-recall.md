# Wake-Up & Recall — Context Loading

Loads a compact context block (~600–900 tokens) into the AI agent at session start: agent identity and the most important project facts. On-demand recall loads more from specific wings/rooms mid-conversation.

---

## Two Levels of Context

### Level 0+1: Wake-Up (Identity + Essential Story)

`wake_up` loads a compact context block (~600–900 tokens) containing:
- **L0 — Agent identity**: who the agent is, what project it's working on
- **L1 — Essential story**: the most important facts about the project (architecture, conventions, recent decisions)

This is the "system prompt primer" — enough context for the agent to be useful immediately.

```bash
$ pneuma wakeup
# Returns identity + essential context for all wings

$ pneuma wakeup code
# Scoped to the code wing only
```

### Level 2: Recall (On-Demand Retrieval)

`recall` loads additional context from specific wings/rooms when the agent needs deeper knowledge mid-conversation.

```
Tool: recall
  wing: "chat"
  room: "decisions"
  n_results: 10
```

This is for when the agent is about to work on authentication and needs to recall all architecture decisions about auth.

## How It Works

```
Session Start
    │
    ▼
wake_up(wing?)
    │
    ├── L0: Agent identity
    │   "I am the coding assistant for project X"
    │
    └── L1: Essential story
        "Key facts: uses JWT auth, PostgreSQL, deployed on AWS..."
        (~600-900 tokens)
    │
    ▼
Agent begins work
    │
    ▼ (mid-conversation, needs more context)
recall(wing="code", room="src")
    │
    └── L2: On-demand retrieval
        Returns latest entries from the project's src room
```

## Usage

### CLI

```bash
# Full wake-up (all wings)
pneuma wakeup

# Scoped wake-up
pneuma wakeup code          # scoped to code wing
pneuma wakeup chat          # scoped to chat wing
```

### MCP Tools

The MCP server exposes `wake_up()` and `recall()` as helper functions that other tools can use. The agent can also use `search_memory` for targeted retrieval.

**Wake-up flow:**

```
1. Agent starts conversation
2. Agent calls search_memory or reads wake-up context
3. Agent is primed with project knowledge
4. User asks a question
5. Agent already knows project conventions → better answers
```

**Recall flow:**

```
1. User: "How do we handle rate limiting?"
2. Agent calls search_memory("rate limiting", wing="code", room="src")
3. Agent gets specific entries about rate limiting implementation
4. Agent answers with project-specific context
```

## Token Budget

Wake-up is designed to be compact:

| Level | Typical Size | Purpose |
|-------|-------------|---------|
| L0 | ~50 tokens | Agent identity |
| L1 | 600–900 tokens | Essential project story |
| L2 | Variable | On-demand, user-triggered |

The combined L0+L1 output fits comfortably in a system prompt without consuming significant context window space.

## Compared to raw MemPalace

MemPalace has wake-up primitives, but without Pneuma:
- No CLI command to quickly load context
- No MCP integration for AI agents to self-prime
- No wing-scoped wake-up filtering
- No structured L0/L1/L2 layering for token-efficient context loading
