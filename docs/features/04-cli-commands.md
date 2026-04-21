# CLI Commands

23 subcommands for managing, querying, and controlling the knowledge base from the terminal. Most of these you rarely need — mining runs on session start, optimization runs in the background, and the MCP tools handle queries from your IDE. The CLI is mainly for first-time setup, inspection, and manual overrides.

---## Quick Reference

| Command | Purpose |
|---------|--------|
| `pneuma quickstart [path]` | First-time setup: scaffold config, init, IDE setup, doctor |
| `pneuma init [path]` | Scan project, create palace, mine codebase |
| `pneuma mine [path]` | Re-mine an existing palace (incremental by default) |
| `pneuma status [-v]` | Show palace stats; `-v` previews entries |
| `pneuma wakeup [wing]` | Load agent identity + essential context |
| `pneuma search <query>` | Semantic search with filters |
| `pneuma explore [room]` | Walk the palace graph or show the full map |
| `pneuma bridges [wing_a] [wing_b]` | Find rooms that bridge wings |
| `pneuma diary read\|write` | Agent journal entries |
| `pneuma timeline [entity]` | Chronological knowledge graph view |
| `pneuma optimize` | Dedup + stale cleanup |
| `pneuma facts <entity>` | Query entity relationships |
| `pneuma import <file>` | Import documents/text |
| `pneuma setup <ide>` | Generate MCP config for VS Code, Cursor, or Claude Code |
| `pneuma doctor` | Verify installation and configuration |
| `pneuma info` | Show active palace, config sources, and environment |
| `pneuma show <entry_id>` | Print full content + metadata for a specific entry |
| `pneuma recent [-n N] [-w wing]` | List recently ingested entries |
| `pneuma reset [path]` | Delete a project's palace completely |
| `pneuma config {show\|init}` | View or scaffold `.pneuma.yaml` config |
| `pneuma test-slack` | Verify Slack integration end-to-end |
| `pneuma test-teams` | Verify Teams integration end-to-end |
| `pneuma logs [-n N] [--follow]` | Tail the MCP server log file |

## Commands in Detail

### `pneuma quickstart [path] [--ide IDE] [-y]`

First-time setup in one command: scaffolds `.pneuma.yaml`, pauses for you to review it, then runs `init`, IDE setup, and `doctor`.

```bash
$ pneuma quickstart /path/to/project          # auto-detect IDE, pause for config review
$ pneuma quickstart /path/to/project --yes    # skip prompt, use defaults (CI-friendly)
$ pneuma quickstart . --ide cursor            # force Cursor config
```

| Flag | Default | Description |
|------|---------|-------------|
| `path` | `.` | Project root to initialize |
| `--ide` | `auto` | `vscode`, `cursor`, `claude-code`, or `auto` |
| `-y` / `--yes` | off | Skip the `.pneuma.yaml` edit prompt |

### `pneuma init [path] [--dry-run]`

Scans a project directory, detects languages and frameworks, creates a wing/room layout that mirrors the project's top-level directories, and mines every source file into the palace.

```bash
$ pneuma init .
Scanning project: /home/dev/myapp
  Mining codebase — 847 files, 2341 chunks stored...

Complexity : medium
Languages  : python, typescript
Frameworks : python-project, node
Template   : auto-medium
Palace dir : ~/.pneuma/palaces/myapp
Top-level dirs: src, tests, docs, scripts

Collections:
  code/src, code/tests, code/docs, code/scripts, code/general
  chat/decisions, chat/conventions
  chat/solutions, chat/workarounds, chat/context, chat/escalations

Codebase mined:
  Files processed : 847
  Chunks stored   : 2341
  Summaries stored: 847
  Files skipped   : 396
```

**Flags:**
- `--dry-run` — preview layout and routing without writing anything

### `pneuma mine [path] [--dry-run] [--full]`

Manual override for re-mining. **Normally you don't need this** — Pneuma automatically re-mines in the background on every session start (`wake_up`). Use this command after a large `git pull`, branch switch, or when you want to force an immediate sync.

```bash
$ pneuma mine
[INCREMENTAL] Mining codebase: /home/dev/myapp
  [INCREMENTAL] 12 files, 47 chunks stored...

    Processed : 12 files
    Stored    : 47 chunks
    Stored    : 12 summaries
    Skipped   : 0 files
  Unchanged   : 835 files (hash match, skipped)
    Removed   : 3 files (deleted from disk)
```

**Flags:**
- `--full` — force complete re-mine (ignore state DB)
- `--dry-run` — show what would be mined without writing

First run takes as long as `pneuma init`. Subsequent incremental runs complete in seconds for typical dev-day changes.

**Controlling which files are skipped:**
Create `.pneuma.yaml` at the project root to add skip patterns, exclude generated files, or set a priority order:

```yaml
miner:
  skip:
    - "third_party/**"
    - "**/*_generated.*"
  generated:
    - "*.pb.go"
    - "*.bundle.js"
  priority:
    - "README.md"
    - "docs/**"
```

`.gitignore` patterns are respected automatically (`respect_gitignore: true` by default). Copy [`.pneuma.yaml.example`](../../.pneuma.yaml.example) from the repo root for a fully-annotated starting point. See [Codebase Mining](../mining.md) for all options.

### `pneuma status [-v]`

```bash
$ pneuma status
Project     : /home/dev/myapp
Complexity  : medium
Template    : auto-medium
Palace path : ~/.pneuma/palaces/myapp/palace

Wings (4):

  code (3188 entries)
    src                                       1847 entries
    tests                                      723 entries
    docs                                       418 entries
    general                                    200 entries

  chat (186 entries)
    decisions                                   47 entries
    solutions                                   89 entries
    workarounds                                 32 entries
    ...
```

Pass `-v` / `--detail` to preview up to 3 entries per room.

### `pneuma wakeup [wing]`

Loads the agent's identity and essential story context — outputs a compact block suitable for use as a system prompt prefix.

```bash
$ pneuma wakeup
# Returns ~600-900 tokens of identity + essential context

$ pneuma wakeup code
# Scoped to the "code" wing only
```

### `pneuma search <query> [-n N] [-w wing] [-r room]`

Semantic search across the knowledge base.

```bash
$ pneuma search "how do we handle auth tokens"
[0.87] chat/decisions
  We decided to use JWT tokens with 1-hour expiry...

[0.72] chat/solutions
  Problem: Auth tokens expiring during long-running jobs
  Solution: Implement token refresh middleware...

$ pneuma search "database migration" -n 10 -w chat -r decisions
$ pneuma search "rate limiting" -w code -r src
```

### `pneuma explore [room] [-n hops]`

Walk the palace graph from a room, or show the full palace map when no room is given.

```bash
$ pneuma explore
Palace map:
  [code]  (3188 entries)
    └─ src                                    1847 entries
    └─ tests                                   723 entries
    ...

$ pneuma explore src
Graph traversal from 'src' (max 2 hops):
  ● src       [code]  1847 entries
    └─ tests  [code]   723 entries
    ...
```

### `pneuma bridges [wing_a] [wing_b]`

Find rooms that bridge two wings — topics spanning multiple knowledge domains.

```bash
$ pneuma bridges
Cross-wing bridges (3 found):
  context          bridges: code, chat  (12 entries)
```

| Flag | Description | Default |
|------|-------------|---------|
| `-n` / `--top-k` | Maximum results | 5 |
| `-w` / `--wing` | Filter to wing | all |
| `-r` / `--room` | Filter to room | all |

### `pneuma diary {read|write}`

Personal journal for tracking observations and context.

```bash
# Write an entry
$ pneuma diary write "Migrated auth to JWT tokens today"
$ pneuma diary write "Fixed N+1 query in orders" -t performance

# Read recent entries
$ pneuma diary read
$ pneuma diary read -a copilot -n 20
```

| Flag | Default |
|------|---------|
| `-a` / `--agent` | `pneuma` |
| `-t` / `--topic` | `general` |
| `-n` / `--last-n` | `10` |

### `pneuma timeline [entity]`

Chronological view of knowledge graph facts.

```bash
$ pneuma timeline
2026-01-15 auth-service → uses → session-cookies [EXPIRED 2026-03-01]
2026-03-01 auth-service → uses → JWT
2026-03-15 billing-api → depends-on → stripe-sdk

$ pneuma timeline "auth-service"
# Shows only facts about auth-service
```

### `pneuma optimize`

Manual override for deduplication and stale entry cleanup. **Normally you don't need this** — Pneuma automatically optimizes in the background (every 50 saves or every 7 days). Use this after a large bulk import when you want immediate cleanup.

```bash
$ pneuma optimize
Scanned: 12 collections
Duplicates merged: 7
Stale entries removed: 3
```

| Threshold | Default | Env Override |
|-----------|---------|-------------|
| Similarity | 0.92 | `REFACTOR_SIMILARITY_THRESHOLD` |
| Stale days | 90 | `REFACTOR_STALE_DAYS` |

### `pneuma facts <entity> [--as-of DATE]`

Query the knowledge graph for entity relationships.

```bash
$ pneuma facts "auth-service"
auth-service → uses → JWT (since 2026-03-01, confidence: 1.0)
auth-service → exposes → /api/v2/auth (since 2026-02-10)
billing-api → calls → auth-service (since 2026-01-05)

$ pneuma facts "database" --as-of 2026-01-15
# Shows facts as they were on that date
```

### `pneuma import <file> [--type TYPE] [--wing W] [--room R]`

Import documents or text. See [On-Demand Import](02-on-demand-import.md) for full details.

```bash
$ pneuma import decisions.md --type decision
$ pneuma import slack_export.json --type chat-history
$ pneuma import --text "We decided to use PostgreSQL"
$ echo "raw content" | pneuma import --text -
```

### `pneuma setup <ide>`

Generate MCP configuration for your IDE with auto-detected paths. Supports `vscode`, `cursor`, and `claude-code`.

```bash
$ pneuma setup vscode
# Writes .vscode/mcp.json

$ pneuma setup cursor
# Prints JSON to paste into Cursor Settings → MCP Servers

$ pneuma setup claude-code
# Writes .mcp.json at the project root
```

For VS Code and Claude Code, the command creates or merges into the existing config file — other MCP servers in the file are preserved.

### `pneuma doctor`

Verify installation and configuration. Checks palace, environment, MCP server, IDE configs, and Slack tokens/scopes.

```bash
$ pneuma doctor
Palace:
  ✓ Palace directory exists: data/mempalace
  ✓ Palace manifest valid (4 wings configured)

Environment:
  ✓ .env file found

MCP Server:
  ✓ mcp package importable
  ✓ MCP server module importable

IDE Config:
  ✓ VS Code mcp.json configured for pneuma

Slack:
  ⚠ SLACK_BOT_TOKEN not set — Slack tools will not register

All checks passed.
```

Exits with code 0 if all checks pass, 1 if any hard failures.

### `pneuma info`

Show the active palace, registered project, and config sources for the current directory.

```bash
$ pneuma info
Active project : myapp
Palace path    : ~/.pneuma/palaces/myapp/palace
Registry       : ~/.pneuma/registry.json
Config file    : .pneuma.yaml (project root)
```

### `pneuma show <entry_id>`

Print the full content and metadata of a specific entry by ID. IDs appear in `pneuma search` and `pneuma recent` output.

```bash
$ pneuma show drawer_chat_decisions_a3f9c12b
Wing    : chat
Room    : decisions
Added by: pneuma
Content :
  We decided to use JWT tokens with 1-hour expiry and a refresh token
  strategy. Session cookies were rejected due to scaling concerns.
```

### `pneuma recent [-n N] [-w wing]`

List the most recently ingested entries across the palace. Useful for checking what was just imported or mined.

```bash
$ pneuma recent
$ pneuma recent -n 50
$ pneuma recent -w chat
```

| Flag | Default |
|------|---------|
| `-n` / `--last-n` | `20` |
| `-w` / `--wing` | all wings |

### `pneuma reset [path] [--yes]`

Delete a project's palace completely. Prompts for confirmation unless `--yes` is passed. The project is also removed from the registry.

```bash
$ pneuma reset
$ pneuma reset /path/to/project --yes
```

> This is irreversible. All stored knowledge for the project is deleted.

### `pneuma config {show|init} [--format yaml|json]`

View or scaffold the per-project `.pneuma.yaml` config file.

```bash
# Print the effective miner config (merged defaults + project file)
$ pneuma config show

# Scaffold a .pneuma.yaml at the project root
$ pneuma config init
$ pneuma config init --format json
```

### `pneuma test-slack`

Verify Slack integration end-to-end: checks tokens, resolves the default channel, and posts a test message.

```bash
$ pneuma test-slack
✓ SLACK_BOT_TOKEN found
✓ Channel resolved: #general (C01ABC123)
✓ Test message posted successfully
```

### `pneuma test-teams`

Verify Microsoft Teams integration end-to-end: checks credentials and posts a test message.

```bash
$ pneuma test-teams
✓ TEAMS_CLIENT_ID found
✓ Test message posted successfully
```

### `pneuma logs [-n N] [--follow]`

Tail the MCP server log file (`~/.pneuma/mcp-server.log`).

```bash
$ pneuma logs
$ pneuma logs -n 100
$ pneuma logs --follow    # stream new lines as they arrive
```

| Flag | Default |
|------|---------|
| `-n` / `--lines` | `50` |
| `--follow` | off |

## Compared to raw MemPalace

MemPalace has no CLI. All operations require Python code:

```python
# Without Pneuma — you write Python
from mempalace import MemPalaceStack
stack = MemPalaceStack()
results = stack.tool_search_drawers("auth tokens", n_results=5)
```

```bash
# With Pneuma — one command
pneuma search "auth tokens"
```
