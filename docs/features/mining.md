# Codebase Mining

> How Pneuma ingests your source code into the palace.

Pneuma's miner turns a project directory into searchable knowledge. It runs automatically on `pneuma init` and then **re-runs in the background on every IDE session** (triggered by `wake_up`) — you don't need to invoke it manually.

---

## What the miner does

For each source file, the miner:

1. **Classifies** it — language, kind (code / test / config / doc / script)
2. **Chunks** it — one chunk per function/class/module (tree-sitter) or per 1500-char window (fallback)
3. **Builds a summary** — path + imports + doc + symbol list → one concise overview entry per file
4. **Routes** everything to the right room — based on top-level directory
5. **Tags** each entry with rich metadata for filtering

Every entry goes into the palace with a small metadata dict:

```python
{
    "source_file": "src/auth/jwt.rs",
    "language": "rust",
    "kind": "code",            # code | test | config | doc | script | summary
    "top_level_dir": "src",
    "mtime": 1714060800.0,
    "size": 4523,
    "content_hash": "a1b2c3d4e5f6...",
    "chunk_index": 2,
    "total_chunks": 3,
    "chunk_kind": "function",  # function | class | module | interface | ... | char
    "symbol": "JwtValidator::verify",  # when tree-sitter extracts it
}
```

---

## Room layout

All code goes into the `code` wing. Rooms mirror the project's top-level directories.

Two special rules apply regardless of project:
- Dirs named `tests`, `test`, `spec` → room `tests` (canonical, stable across projects)
- Dirs named `docs`, `doc` → room `docs` (canonical)

Large top-level dirs (≥ 5 immediate subdirs) expand to depth-2 rooms: `iclbase/authorization/` → `code/iclbase-authorization`.

Example for a typical web project:

```
palace
├── code               ← project code (always named "code")
│   ├── src
│   ├── tests          ← canonical
│   ├── docs           ← canonical
│   ├── scripts
│   ├── config
│   ├── migrations
│   └── general        ← files at project root
└── chat               ← shared wing (Slack/Teams + keyword router)
    ├── decisions
    ├── conventions
    ├── solutions
    ├── workarounds
    ├── escalations
    └── context
```

---

## Chunking

### Symbol-level (tree-sitter, preferred)

When `tree-sitter` + `tree-sitter-language-pack` are installed:

```bash
pip install -e .[mining]
```

Each function, class, method, interface, trait, impl, or module becomes its own chunk. Metadata includes the symbol name and kind.

Supported: Python, JavaScript, TypeScript, TSX, Java, Kotlin, C#, Go, Rust, Ruby, PHP, Swift, C/C++, Lua, Scala, Elixir.

### Character-based (fallback)

Without tree-sitter, the miner chunks at 1500 chars with 150 overlap. No symbol metadata, but works on any text file.

---

## File-level summaries

Every mined file also produces one **summary entry** alongside its chunks. Summaries are short (≤ 2500 chars) and contain:

```
File: src/auth/jwt.rs
Language: rust | Kind: code | Dir: auth
Size: 4523 bytes | Chunks: 3

Doc:
  JWT token validation and refresh logic.

Imports:
  use serde::{Deserialize, Serialize};
  use chrono::{DateTime, Utc};

Symbols:
  struct: JwtValidator
  function: verify
  function: refresh
  enum: TokenError
```

Summaries fix the "broad query" problem — queries like *"what does the auth module do?"* now match the summary instead of random chunks.

---

## Per-project configuration

Create `.pneuma.yaml` (or `.pneuma.json`) at the project root to override defaults. A fully-annotated example is included in the repo as [`.pneuma.yaml.example`](../.pneuma.yaml.example) — copy and rename it to get started:

```bash
cp .pneuma.yaml.example .pneuma.yaml
```

**Example** `.pneuma.yaml`:

```yaml
miner:
  chunk_size: 3000
  chunk_overlap: 200
  max_file_size: 200000
  respect_gitignore: true

  # Extra patterns to skip (gitignore-style globs)
  skip:
    - "third_party/**"
    - "**/*_generated.*"
    - "docs/archive/**"

  # Generated-file patterns (replaces defaults)
  generated:
    - "*.pb.go"
    - "*.bundle.js"
    - "*-bundle.js"

  # Priority order — these mined first
  priority:
    - "README.md"
    - "ARCHITECTURE.md"
    - "docs/**"
```

YAML requires `pyyaml`: `pip install -e .[yaml]`. If it's not installed, use `.pneuma.json` with the same structure.

| Key | Default | Description |
|---|---|---|
| `chunk_size` | `1500` | Chars per chunk (char-based fallback only) |
| `chunk_overlap` | `150` | Overlap between consecutive chunks |
| `max_file_size` | `100_000` | Bytes — files larger than this are skipped |
| `max_files` | `5_000` | Safety cap on total files mined |
| `workers` | `4` | Files processed concurrently — raise to 8–16 for large codebases |
| `respect_gitignore` | `true` | Apply `.gitignore` patterns as skip rules |
| `skip` | `[]` | Extra gitignore-style skip patterns |
| `generated` | defaults | Filename globs always treated as generated (overrides defaults if set) |
| `priority` | `[]` | Patterns to mine first — useful for docs + READMEs |

---

## Default skip behaviour

**Directories skipped always:**
`.git`, `__pycache__`, `node_modules`, `.venv`, `venv`, `env`, `.tox`, `dist`, `build`, `.mypy_cache`, `.pytest_cache`, `.next`, `target`, `.idea`, `.vs`, `obj`, `out`, `coverage`, `vendor`, `third_party`, `external`, others

**Generated files skipped by default:**
- `*.pb.go`, `*.pb.py`, `*.pb.cc`, `*.pb.h` — protobuf output
- `*_pb2.py`, `*_pb2_grpc.py` — grpc Python
- `*.min.js`, `*.min.css`, `*.bundle.js`, `*.bundle.css`
- `*.generated.*`, `*_generated.*`
- `*.map`, `*.d.ts.map`

**Lockfiles skipped:**
`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `Cargo.lock`, `poetry.lock`, `Gemfile.lock`, `composer.lock`

**Binary extensions skipped:**
`.exe`, `.dll`, `.so`, `.bin`, `.obj`, `.jpg`, `.png`, `.pdf`, `.db`, `.sqlite`, etc.

---

## Dry run

Preview what would be mined without writing anything:

```bash
pneuma init . --dry-run
pneuma mine --dry-run
```

Output includes skip breakdown and routing distribution:

```
[DRY RUN] Scanning project: /path/to/myproj

Complexity     : large
Top-level dirs : src, tests, docs, scripts
Wings would be : code, chat

  Would process : 847 files
  Would store   : 2341 chunks
  Would store   : 847 summaries
  Skipped       : 396 files

Skip breakdown:
  binary                         231
  unknown-extension              112
  generated                       53

Route breakdown (wing/room → chunks):
  code/src                       1204
  code/tests                      623
  code/docs                       514
```

---

## Incremental re-mining

After the first `pneuma init`, Pneuma **automatically re-mines in the background** whenever your AI assistant calls `wake_up` at the start of a session. Incremental mode means only changed files are re-embedded — typically 1–3 seconds for a normal dev day.

If you want to trigger a re-mine manually (e.g., after a large `git pull`):

```bash
pneuma mine              # incremental — only changed files re-embedded
pneuma mine --full       # force full re-mine
pneuma mine --dry-run    # preview without writing
```

Incremental mode:
- Skips files whose content hash matches the stored hash (`files_unchanged`)
- Deletes old entries before re-mining changed files
- Deletes entries for files that were removed from disk (`files_removed`)

State lives in `<palace_dir>/mined_files.sqlite3`. Delete it to force a clean re-mine (or use `--full`).

**Typical timings (1 000-file project):**

| Command | Time |
|---|---|
| First `pneuma init` | ~60–120 s (embeds everything) |
| `pneuma mine` after 3 file changes | ~1–3 s |
| `pneuma mine --full` | ~60–120 s |
| `pneuma mine --dry-run` | ~1 s (no embeddings) |

---

## MCP tool

Agents can trigger mining via the `mine_codebase` tool:

```
mine_codebase()                              # incremental, writes entries
mine_codebase(dry_run=True)                  # preview
mine_codebase(full=True)                     # force complete re-mine
mine_codebase(project_path="/absolute/path") # mine a different project
```

---

## Tips

- **Start with a dry run** — catch unexpected skip/routing outcomes before committing to a full embed
- **Use `priority` for docs** — matches come early when relevance ties
- **Keep `chunk_size` between 1500–3000 for code** — larger chunks dilute similarity; smaller chunks lose context
- **Install `[mining]` for symbol-level chunks** — significant retrieval quality improvement on supported languages
- **`pneuma mine` runs automatically** — the background scheduler handles re-mining on session start; only use the CLI after major changes like a large `git pull` or branch switch when you want to be sure

## Large codebases

For projects with thousands of files, mining can take a long time on the first run. Two config knobs help:

```yaml
miner:
  workers: 8          # default 4 — each worker chunks + embeds one file in parallel
  skip:
    - "tests/**"      # skip test trees you don't need indexed
    - "vendor/**"
    - "generated/**"
  max_file_size: 50000  # lower the ceiling to skip unusually large files faster
```

`workers` is the most impactful setting. sentence-transformers releases the Python GIL during embedding, so multiple workers genuinely run in parallel on all CPU cores. On an 8-core machine, `workers: 8` can cut a 20-minute mine to 3–4 minutes.

Subsequent runs are always fast because incremental mode skips unchanged files (hash check, no re-embedding).
