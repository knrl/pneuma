# Knowledge Graph — Temporal Fact Tracking

Track relationships between entities as typed triples (subject → predicate → object) with validity windows. Query current or historical state.

---

## How It Works

Facts are stored as **triples** (subject → predicate → object) with validity windows:

```
┌─────────────┐     uses       ┌──────────┐
│ auth-service│ ──────────────▶│   JWT    │
└─────────────┘  since 2026-03 └──────────┘
       │
       │ used (expired)
       ▼
┌──────────────────┐
│ session-cookies  │
│ (2026-01 → 2026-03) │
└──────────────────┘
```

Each fact has:
- **Subject** — the entity (e.g., `auth-service`)
- **Predicate** — the relationship (e.g., `uses`, `depends-on`, `deployed-to`)
- **Object** — the target (e.g., `JWT`, `PostgreSQL`, `AWS`)
- **Valid From** — when the fact became true
- **Valid To** — when it stopped being true (null = still current)
- **Confidence** — how certain the fact is (0.0–1.0)

## Usage

### MCP Tools (AI Agent)

**`track_fact`** — Record a new fact:

```
Tool: track_fact
  subject: "auth-service"
  predicate: "uses"
  value: "JWT"
  valid_from: "2026-03-01"
  confidence: 1.0
```

**`query_facts`** — Look up an entity:

```
Tool: query_facts
  entity: "auth-service"
  direction: "both"
```

Returns:

```
auth-service:
  → uses → JWT (since 2026-03-01, confidence: 1.0)
  → exposes → /api/v2/auth (since 2026-02-10)
  ← depends-on ← billing-api (since 2026-01-05)

Expired:
  → uses → session-cookies (2026-01-15 → 2026-03-01)
```

**`invalidate_fact`** — Mark a fact as no longer true:

```
Tool: invalidate_fact
  subject: "auth-service"
  predicate: "uses"
  value: "session-cookies"
  ended: "2026-03-01"
```

**`query_facts`** with chronological view:

```
Tool: query_facts
  entity: "auth-service"
  chronological: true
```

Returns facts ordered by time, showing validity windows and current vs. expired status.

**`palace_overview(detail="full")`** — Includes a KG summary section:

```
Tool: palace_overview
  detail: "full"
```

The "full" view appends a Knowledge graph block:

```
Knowledge graph:
  Entities       : 24
  Total facts    : 67
  Current facts  : 52
  Expired facts  : 15
  Relationship types: uses, depends-on, deployed-to, implements, exposes
```

> Note: the standalone `knowledge_stats` MCP tool was removed in favour of
> `palace_overview(detail="full")` to keep the tool surface small.

### CLI

```bash
# Query an entity
$ pneuma facts "auth-service"
auth-service → uses → JWT (since 2026-03-01, confidence: 1.0)
auth-service → exposes → /api/v2/auth (since 2026-02-10)
billing-api → depends-on → auth-service (since 2026-01-05)

# Query as of a past date
$ pneuma facts "auth-service" --as-of 2026-02-01
auth-service → uses → session-cookies (since 2026-01-15)

# View timeline
$ pneuma timeline
2026-01-15 auth-service → uses → session-cookies [EXPIRED 2026-03-01]
2026-02-10 auth-service → exposes → /api/v2/auth
2026-03-01 auth-service → uses → JWT

$ pneuma timeline "billing-api"
```

## Use Cases

### Architecture Awareness

The AI agent tracks facts about your system as it learns:

```
User: "We just migrated to PostgreSQL for billing"
Agent: track_fact("billing-service", "uses", "PostgreSQL", valid_from="2026-04-19")
Agent: invalidate_fact("billing-service", "uses", "MySQL", ended="2026-04-19")
```

Now when someone asks "what database does billing use?", the agent gives the current answer — not the stale one.

### Impact Analysis

Before a change, query related facts:

```
Agent: query_facts("PostgreSQL")
→ billing-service uses PostgreSQL
→ analytics-pipeline reads-from PostgreSQL
→ user-service depends-on PostgreSQL

Agent: "Changing the PostgreSQL schema will affect billing-service,
        analytics-pipeline, and user-service."
```

### Decision History

Track why things changed:

```
track_fact("auth-service", "decided-against", "OAuth2", confidence=0.9)
track_fact("auth-service", "reason", "too complex for internal services")
```

Later:

```
User: "Should we use OAuth2?"
Agent: query_facts("OAuth2")
→ auth-service decided-against OAuth2 (confidence: 0.9)
→ reason: "too complex for internal services"
Agent: "The team previously decided against OAuth2 — it was deemed too complex
        for internal services."
```

### Time-Travel Queries

Check what was true at a specific point in time:

```bash
$ pneuma facts "auth-service" --as-of 2026-02-01
# Shows only facts valid on 2026-02-01
# session-cookies was still in use, JWT hadn't been adopted yet
```

## Storage

Facts are stored in a SQLite knowledge graph at `~/.mempalace/knowledge_graph.sqlite3`. This is separate from the ChromaDB vector store — the KG is for structured relationships, ChromaDB is for semantic search.

## Compared to raw MemPalace

MemPalace has a knowledge graph primitive, but without Pneuma:
- No MCP tools for AI agents to track/query facts
- No CLI commands (`facts`, `timeline`)
- No `invalidate_fact` workflow for temporal tracking
- No `--as-of` time-travel queries
- No knowledge stats overview
