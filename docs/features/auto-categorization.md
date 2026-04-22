# Auto-Categorization — Content Routing

Content stored through Pneuma is routed to a wing and room based on its type. Code files are routed by directory; chat messages, imports, and saved knowledge are routed by a keyword classifier.

Pneuma has **two separate routing strategies** because code and chat knowledge have different natural organizations:

| Source | Router | Routes to |
|---|---|---|
| Source code files (via `pneuma init` / `pneuma mine`) | **Directory-based** | `code/<top-level-dir>` |
| Slack/Teams messages, imported docs, `save_knowledge` calls | **Keyword-based** | `chat/decisions`, `chat/solutions`, `chat/escalations`, … |

---

## Code routing — directory-mirroring

When Pneuma mines your codebase, each file is routed by its top-level directory:

```
src/auth/jwt.rs          → code/src
tests/unit/test_auth.py  → code/tests   (canonical — always "tests" regardless of dir name)
docs/architecture.md     → code/docs    (canonical — always "docs")
README.md                → code/general (project root)
iclbase/http/server.cpp  → code/iclbase-http  (depth-2: iclbase has many subdirs)
```

See [Codebase Mining](mining.md) for full details including canonical rooms and two-level mirroring.

### Why this way?

- Directory layout is how humans navigate the codebase — querying with the same mental model works
- Scoping a search to `wing=code, room=src` is surgical and matches the actual module boundary
- Top-level directory names are free annotations — `rust_ffi/`, `migrations/`, `iclbase/` all tell you something
- `tests` and `docs` are always named consistently across all projects for cross-project search

---

## Chat / document routing — keyword classifier

Non-code content (Slack messages, Teams messages, markdown imports, explicit `save_knowledge` calls) goes through the keyword router in `core/auto_org/router.py`:

```
"We decided to use JWT instead of session cookies"
    │
    ▼
  Router: contains "decided" → (chat, decisions)
    │
    ▼
  Stored in: chat/decisions
```

### Routing rules

The router checks content against keywords in priority order. The first match wins:

| Priority | Keywords | Wing | Room |
|----------|----------|------|------|
| 1 | `escalate`, `help needed`, `blocked`, `stuck`, `can't figure` | chat | escalations |
| 2 | `decided`, `decision`, `we agreed`, `convention`, `standard`, `architecture` | chat | decisions |
| 3 | `style guide`, `naming convention`, `lint`, `format` | chat | conventions |
| 4 | `workaround`, `hack`, `temp fix`, `temporary`, `hotfix` | chat | workarounds |
| 5 | `solution`, `solved`, `fixed`, `answer`, `resolved` | chat | solutions |
| — | (no match) | chat | context |

The code wing is dynamic and filled by the miner, not the keyword router. Code-related keywords (`api`, `function`, `class`, etc.) are not handled by this router.

### Override routing

You can always bypass the router by specifying wing/room explicitly:

**CLI:**
```bash
pneuma import notes.md --wing chat --room decisions
```

**MCP tool:**
```
Tool: save_knowledge
  content: "We decided to use token bucket rate limiting"
  wing: "chat"
  room: "decisions"
```

When wing/room are provided, the router is bypassed.

---

## Palace layout after init

`pneuma init` creates two wings:

```
code                         ← one room per top-level directory of your project
  ├─ src, tests, docs, ...  (populated by the code miner)
  └─ general                (files at project root)

chat                        ← populated by Slack/Teams ingestion + keyword router
  ├─ decisions
  ├─ conventions
  ├─ solutions
  ├─ workarounds
  ├─ escalations
  └─ context
```

The `code` wing is **dynamic** — rooms mirror your actual directory structure. The `chat` wing is **fixed** with six semantic rooms covering all team knowledge types.

---

## How this improves retrieval

Organized entries improve search quality in two ways:

**1. Scoped queries cut noise**

```
Search: "how do we handle rate limiting"

Unscoped (all wings):
  [0.72] code/src        — code chunk from rate limiter
  [0.70] chat/decisions  — "We decided to use token bucket"
  [0.68] chat/workarounds — "Workaround: disabled on staging"

Scoped:  search "rate limiting" -w chat -r decisions
  [0.70] chat/decisions  — "We decided to use token bucket"
```

**2. Structural precision matches directory**

```
Search: "JWT validation"  -w code -r src
  [0.88] code/src  — src/auth/jwt.rs  (focused, module-scoped)
```

---

## Compared to raw MemPalace

MemPalace stores entries in wings/rooms, but:
- No automatic keyword classification for chat content
- No noise filtering or PII stripping before storage
- No escalation wing for confidence-based routing
- No complexity-based template selection — you pick rooms manually
