# Optimization Engine

Multi-stage pipeline that deduplicates entries, removes stale content, checks index health, detects contradictions, and optionally compresses and rebuilds the index. Runs automatically in the background; also available via `pneuma optimize`.

---

## How It Works

The optimization engine (`core/auto_org/refactor.py`) runs a multi-stage pipeline with two levels:

### Standard Level (5 stages)

Safe for automatic background runs. No heavy or destructive operations.

#### Stage 1: Batch Deduplication

Uses MemPalace's embedding-based batch dedup (`mempalace.dedup`) to find near-duplicates by cosine distance within source-file groups. Far more efficient than per-entry comparison — operates in batch using ChromaDB's native vectors.

```
Entry A: "Reset staging DB: run `rails db:reset` then seed with `rake db:seed`"
Entry B: "To reset the staging database, use `rails db:reset` followed by `rake db:seed`"

Cosine similarity: 0.94 (> 0.92 threshold)
→ Entry B removed (duplicate of A)
```

**Threshold:** `0.92` similarity (configurable via `REFACTOR_SIMILARITY_THRESHOLD`)

#### Stage 2: Stale Entry Removal

Entries older than 180 days (based on `ingested_at` or `filed_at` timestamp) are deleted permanently. This is age-only — retrieval count is not tracked, so the threshold was raised from an earlier 90-day default to avoid over-pruning.

**Threshold:** `180` days (configurable via `REFACTOR_STALE_DAYS`)

#### Stage 3: Index Health Scan

Scans the HNSW index for corrupt or unfetchable IDs using `mempalace.repair.scan_palace()`. If corrupt IDs are found (and not in dry-run mode), they're pruned directly from the collection.

#### Stage 4: Fact Check

Samples up to 100 recent entries and checks each against the knowledge graph using `mempalace.fact_checker.check_text()` for:

- **Similar names** — entity names with edit distance ≤ 2 (e.g., "auth_service" vs "auth-service")
- **Relationship mismatches** — KG records a different relationship than what the entry claims
- **Stale facts** — KG marks the referenced fact as expired

Contradictions are **reported only** — no auto-deletion (they need human judgment).

#### Stage 5: Indexing Status

Queries ChromaDB's `get_indexing_status()` to report how many operations are pending indexing. Informational — useful to know if recent bulk writes haven't been fully indexed yet.

### Deep Level (adds 4 more stages)

Heavy and/or destructive operations. **Only runs via CLI** — the MCP tool forces deep to dry-run mode to prevent AI agents from autonomously triggering destructive operations.

#### Stage 6: AAAK Compression

Compresses uncompressed entries (≥ 200 chars) using MemPalace's AAAK dialect (`mempalace.dialect.Dialect.compress()`). Purely rule-based — no LLM needed. Skips entries already marked as compressed.

#### Stage 7: Index Rebuild

Rebuilds the HNSW index from scratch via `mempalace.repair.rebuild_index()`: extracts all drawers, drops the collection, recreates it with correct HNSW settings, and upserts everything back. Reclaims space from accumulated deletes.

#### Stage 8: Migration Check

Checks if the ChromaDB database version matches the installed ChromaDB version. If a mismatch is detected and not in dry-run mode, runs `mempalace.migrate.migrate()` to upgrade.

#### Stage 9: Cache Clear

Calls `ChromaDB.clear_system_cache()` after rebuild/migration to ensure a clean state.

## Triggers

### Automatic (background)

Optimization runs automatically — level `standard` only. The background scheduler in `core/background.py` fires when either condition is met:

- **Every 50 writes** — counts all agent write paths: `save_knowledge`, `import_content`, `mine_codebase`, and `ingest_chat_channel`. Bulk operations count by entries written (e.g., importing 30 entries = 30 toward the threshold).
- **Every 7 days** — time-based floor so the palace stays clean even in quiet periods.

State persists in `~/.pneuma/scheduler_state.json`. Activity logs to `~/.pneuma/mcp-server.log` (`pneuma logs` to tail).

### Manual (CLI)

```bash
pneuma optimize                    # standard level
pneuma optimize --level deep       # all 9 stages
pneuma optimize --dry-run          # preview without writing
pneuma optimize --level deep --dry-run  # preview deep
```

Example output:

```
Duplicates merged        : 7
Stale entries deleted    : 3
Collections scanned      : 12
Index health             : clean
Contradictions           : 2 found
  [similar_name] "auth_service" vs "auth-service" (distance=1)
  [stale_fact] "redis" expired 2026-02-01
Indexing status          : 100% (0 unindexed)

Optimization complete — no errors.
```

### Via MCP Tool

AI agents can call `optimize_memory`:

```
Tool: optimize_memory(level="standard")
→ standard optimization runs normally

Tool: optimize_memory(level="deep")
→ forced to dry-run, agent sees the report + instruction to use CLI for actual deep runs
```

**Security:** `deep` level via MCP is always coerced to `dry_run=True`. Destructive deep operations (index rebuild, migration, compression) require human-initiated CLI.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `REFACTOR_SIMILARITY_THRESHOLD` | `0.92` | Cosine similarity above which entries are considered duplicates |
| `REFACTOR_STALE_DAYS` | `180` | Days since ingestion before an entry is permanently deleted |

### Tuning Guidance

- **Lower similarity threshold** (e.g., 0.85): More aggressive dedup, may merge entries that are related but distinct
- **Higher similarity threshold** (e.g., 0.95): Only removes near-identical entries
- **Shorter stale period** (e.g., 30): Faster cleanup, but may remove knowledge that's useful but infrequently needed
- **Longer stale period** (e.g., 365): More conservative, keeps historical knowledge longer

## Technical Details

The optimization engine lives in `core/auto_org/refactor.py`:

```python
@dataclass
class OptimizeReport:
    duplicates_merged: int = 0
    dedup_groups_checked: int = 0
    stale_removed: int = 0
    collections_scanned: int = 0
    index_corrupt_found: int = 0
    index_corrupt_pruned: int = 0
    contradictions: list[dict]
    indexing_progress: float = 1.0
    unindexed_ops: int = 0
    entries_compressed: int = 0       # deep only
    index_rebuilt: bool = False        # deep only
    migration_needed: bool = False     # deep only
    migration_done: bool = False       # deep only
    level: str = "standard"
    errors: list[str]
```

- `run_optimize(dry_run, level)` — Main orchestrator: runs stages 1–5 (standard) or 1–9 (deep)
- `run_refactor(dry_run)` — Legacy wrapper → calls `run_optimize(level="standard")` and maps to `RefactorReport`

**Adapter layer** (`core/palace.py`):

| Function | MemPalace module | Purpose |
|----------|-----------------|---------|
| `batch_dedup()` | `mempalace.dedup` | Batch embedding-based near-duplicate removal |
| `scan_index()` | `mempalace.repair` | Find corrupt HNSW index entries |
| `prune_corrupt_ids()` | Direct ChromaDB | Delete corrupt IDs without file dependency |
| `rebuild_index()` | `mempalace.repair` | Full index extract → drop → recreate → upsert |
| `compress_entry()` | `mempalace.dialect` | AAAK compression (rule-based, no LLM) |
| `check_facts()` | `mempalace.fact_checker` | Contradiction detection against KG |
| `get_indexing_status()` | ChromaDB API | Pending indexing operations |
| `clear_cache()` | ChromaDB API | Internal cache reset |
| `check_migration_needed()` | `mempalace.migrate` | ChromaDB version compatibility check |
| `run_migration()` | `mempalace.migrate` | Run ChromaDB version migration |

## Compared to raw MemPalace

| Capability | MemPalace | Pneuma |
|---|---|---|
| Batch dedup | `mempalace.dedup` (manual CLI) | Automated via Stage 1 with scheduling |
| Index repair | `mempalace.repair` (manual CLI) | Automated scan in Stage 3; rebuild in Stage 7 |
| AAAK compression | `mempalace.dialect` (manual CLI) | Automated in Stage 6 (deep) |
| Contradiction detection | `mempalace.fact_checker` (library) | Automated sampling in Stage 4 |
| Migration | `mempalace.migrate` (manual CLI) | Automated check + run in Stage 8 |
| Stale entry removal | Not provided | Pneuma's Stage 2 (180-day age-based) |
| Auto-scheduling | Not provided | Every 50 writes or 7 days |
| Agent safety guards | Not applicable | Deep forced to dry-run via MCP |
