"""
Optimization engine — unified pipeline for palace maintenance.

Stages (standard):
  1. Batch dedup       — mempalace.dedup (embedding-based, batch)
  2. Stale removal     — age-based entry deletion
  3. Index health      — scan + prune corrupt HNSW IDs
  4. Fact check        — contradiction detection via KG
  5. Indexing status   — ChromaDB index progress

Stages (deep):
  6. AAAK compression  — rule-based text compression
  7. Index rebuild     — extract → drop → recreate → upsert
  8. Migration check   — ChromaDB version compatibility
  9. Cache clear       — ChromaDB internal cache reset
"""

import logging
import time
from dataclasses import dataclass, field

import os

_log = logging.getLogger("pneuma.optimize")

SIMILARITY_THRESHOLD = 0.92
STALE_DAYS = 180  # age-only; retrieval_count is not tracked so 90d was too aggressive
FACT_CHECK_SAMPLE = 100  # max entries to fact-check per run

# Allow env-var overrides
_sim = os.getenv("REFACTOR_SIMILARITY_THRESHOLD")
if _sim:
    SIMILARITY_THRESHOLD = float(_sim)
_stale = os.getenv("REFACTOR_STALE_DAYS")
if _stale:
    STALE_DAYS = int(_stale)


@dataclass
class OptimizeReport:
    """Summary of a full optimization run."""
    # Stage 1: Dedup
    duplicates_merged: int = 0
    dedup_groups_checked: int = 0
    # Stage 2: Stale
    stale_removed: int = 0
    # Shared
    collections_scanned: int = 0
    # Stage 3: Index health
    index_corrupt_found: int = 0
    index_corrupt_pruned: int = 0
    # Stage 4: Fact check
    contradictions: list[dict] = field(default_factory=list)
    # Stage 5: Indexing status
    indexing_progress: float = 1.0
    unindexed_ops: int = 0
    # Stage 6: Compression (deep)
    entries_compressed: int = 0
    # Stage 7: Rebuild (deep)
    index_rebuilt: bool = False
    # Stage 8: Migration (deep)
    migration_needed: bool = False
    migration_done: bool = False
    # Errors & dry-run
    level: str = "standard"
    errors: list[str] = field(default_factory=list)
    would_merge: list[dict] = field(default_factory=list)
    would_archive: list[dict] = field(default_factory=list)
    would_prune: list[str] = field(default_factory=list)


# ── Legacy compat ────────────────────────────────────────────────


@dataclass
class RefactorReport:
    """Legacy report — mapped from OptimizeReport for backward compat."""
    duplicates_merged: int = 0
    stale_archived: int = 0
    collections_scanned: int = 0
    errors: list[str] | None = None
    would_merge: list[dict] | None = None
    would_archive: list[dict] | None = None


def run_refactor(dry_run: bool = False) -> RefactorReport:
    """Legacy entry point — wraps run_optimize(level='standard')."""
    opt = run_optimize(dry_run=dry_run, level="standard")
    return RefactorReport(
        duplicates_merged=opt.duplicates_merged,
        stale_archived=opt.stale_removed,
        collections_scanned=opt.collections_scanned,
        errors=opt.errors or None,
        would_merge=opt.would_merge or None,
        would_archive=opt.would_archive or None,
    )


# ── Main orchestrator ────────────────────────────────────────────


def run_optimize(dry_run: bool = False, level: str = "standard") -> OptimizeReport:
    """
    Unified optimization pipeline.

    Args:
        dry_run: If True, report only — no destructive writes.
        level: ``"standard"`` (safe, suitable for auto-trigger) or
               ``"deep"`` (heavy ops, manual only).

    Returns:
        OptimizeReport with per-stage results.
    """
    report = OptimizeReport(level=level)

    # Stage 1: Batch dedup
    _stage_dedup(report, dry_run)

    # Stage 2: Stale removal
    _stage_stale(report, dry_run)

    # Stage 3: Index health
    _stage_index_health(report, dry_run)

    # Stage 4: Fact check
    _stage_fact_check(report)

    # Stage 5: Indexing status
    _stage_indexing_status(report)

    if level == "deep":
        # Stage 6: AAAK compression
        _stage_compress(report, dry_run)

        # Stage 7: Index rebuild
        _stage_rebuild(report, dry_run)

        # Stage 8+9: Migration check + cache clear
        _stage_migration(report, dry_run)
        _stage_cache_clear(report, dry_run)

    return report


# ── Stage 1: Batch dedup ─────────────────────────────────────────


def _stage_dedup(report: OptimizeReport, dry_run: bool) -> None:
    """Batch dedup: per-source groups first, then cross-source pass."""
    from core.palace import batch_dedup, cross_source_dedup, list_wings

    wings = list_wings()
    if not wings:
        return

    # Convert similarity threshold to cosine distance for mempalace
    distance_threshold = round(1.0 - SIMILARITY_THRESHOLD, 4)

    try:
        # Pass 1: per-source dedup (fast — only compares within same source_file)
        for wing_name in wings:
            result = batch_dedup(
                threshold=distance_threshold,
                dry_run=dry_run,
                wing=wing_name,
            )
            report.dedup_groups_checked += result["groups_checked"]
            report.duplicates_merged += result["deleted"]

            if dry_run:
                for d in result["details"]:
                    report.would_merge.append({
                        "source": d["source"],
                        "keep_count": len(d["kept"]),
                        "drop_count": len(d["deleted"]),
                        "drop_ids": d["deleted"],
                    })

        # Pass 2: cross-source dedup (catches duplicates across different
        # source_files / wings / rooms — e.g., Slack ingestion vs manual save)
        xresult = cross_source_dedup(
            threshold=distance_threshold,
            dry_run=dry_run,
        )
        report.duplicates_merged += xresult["deleted"]
        if dry_run:
            for d in xresult["details"]:
                report.would_merge.append({
                    "source": d["source"],
                    "keep_count": len(d["kept"]),
                    "drop_count": len(d["deleted"]),
                    "drop_ids": d["deleted"],
                })
    except Exception as exc:
        _log.exception("stage/dedup failed")
        report.errors.append(f"dedup: {exc}")


# ── Stage 2: Stale removal ──────────────────────────────────────


def _stage_stale(report: OptimizeReport, dry_run: bool) -> None:
    """Delete entries older than STALE_DAYS."""
    from core.palace import list_wings, list_rooms, list_room_entries, delete_entry

    wings = list_wings()
    if not wings:
        return

    cutoff = time.time() - (STALE_DAYS * 86400)

    for wing_name in wings:
        rooms = list_rooms(wing=wing_name)
        for room_name in rooms:
            report.collections_scanned += 1
            try:
                hits = list_room_entries(wing=wing_name, room=room_name)
                for hit in hits:
                    meta = hit.metadata
                    drawer_id = meta.get("id", "")
                    if not drawer_id:
                        continue

                    ingested_at = _parse_timestamp(meta)
                    if ingested_at is None:
                        continue

                    if ingested_at < cutoff:
                        if dry_run:
                            age_days = (time.time() - ingested_at) / 86400
                            report.would_archive.append({
                                "drawer_id": drawer_id,
                                "age_days": round(age_days, 1),
                                "wing": wing_name,
                                "room": room_name,
                                "preview": hit.content[:100].replace("\n", " "),
                            })
                        else:
                            delete_entry(drawer_id)
                        report.stale_removed += 1
            except Exception as exc:
                _log.exception("stage/stale %s/%s failed", wing_name, room_name)
                report.errors.append(f"stale {wing_name}/{room_name}: {exc}")


def _parse_timestamp(meta: dict) -> float | None:
    """Extract a timestamp from metadata (ingested_at or filed_at)."""
    ingested_at = meta.get("ingested_at", 0)
    try:
        return float(ingested_at)
    except (TypeError, ValueError):
        pass

    filed_at = meta.get("filed_at", "")
    if filed_at:
        try:
            from datetime import datetime
            return datetime.fromisoformat(filed_at).timestamp()
        except (ValueError, TypeError):
            pass
    return None


# ── Stage 3: Index health ───────────────────────────────────────


def _stage_index_health(report: OptimizeReport, dry_run: bool) -> None:
    """Scan for and optionally prune corrupt HNSW index entries."""
    from core.palace import scan_index, prune_corrupt_ids

    try:
        result = scan_index()
        report.index_corrupt_found = result["bad"]

        if result["bad"] > 0:
            if dry_run:
                report.would_prune = result["bad_ids"]
            else:
                pruned = prune_corrupt_ids(result["bad_ids"])
                report.index_corrupt_pruned = pruned
    except Exception as exc:
        _log.exception("stage/index_health failed")
        report.errors.append(f"index_health: {exc}")


# ── Stage 4: Fact check ─────────────────────────────────────────


def _stage_fact_check(report: OptimizeReport) -> None:
    """Sample recent entries and check for contradictions."""
    from core.palace import list_wings, list_rooms, list_room_entries, check_facts

    try:
        wings = list_wings()
        if not wings:
            return

        sampled = 0
        for wing_name in wings:
            if sampled >= FACT_CHECK_SAMPLE:
                break
            rooms = list_rooms(wing=wing_name)
            for room_name in rooms:
                if sampled >= FACT_CHECK_SAMPLE:
                    break
                entries = list_room_entries(wing=wing_name, room=room_name)
                for entry in entries:
                    if sampled >= FACT_CHECK_SAMPLE:
                        break
                    issues = check_facts(entry.content)
                    if issues:
                        for issue in issues:
                            issue["wing"] = wing_name
                            issue["room"] = room_name
                        report.contradictions.extend(issues)
                    sampled += 1
    except Exception as exc:
        _log.exception("stage/fact_check failed")
        report.errors.append(f"fact_check: {exc}")


# ── Stage 5: Indexing status ────────────────────────────────────


def _stage_indexing_status(report: OptimizeReport) -> None:
    """Query ChromaDB for pending indexing operations."""
    from core.palace import get_indexing_status

    try:
        status = get_indexing_status()
        report.indexing_progress = status["progress"]
        report.unindexed_ops = status["unindexed"]
    except Exception as exc:
        _log.exception("stage/indexing_status failed")
        report.errors.append(f"indexing_status: {exc}")


# ── Stage 6: AAAK compression (deep only) ───────────────────────


def _stage_compress(report: OptimizeReport, dry_run: bool) -> None:
    """Compress uncompressed entries using AAAK dialect."""
    from core.palace import (
        list_wings, list_rooms, list_room_entries, compress_entry,
    )
    from mempalace.mcp_server import tool_update_drawer

    try:
        wings = list_wings()
        for wing_name in wings:
            rooms = list_rooms(wing=wing_name)
            for room_name in rooms:
                entries = list_room_entries(wing=wing_name, room=room_name)
                for entry in entries:
                    meta = entry.metadata
                    if meta.get("compressed"):
                        continue
                    if not entry.content or len(entry.content) < 200:
                        continue

                    drawer_id = meta.get("id", "")
                    if not drawer_id:
                        continue

                    compressed = compress_entry(
                        entry.content,
                        metadata={"wing": wing_name, "room": room_name,
                                  "source_file": entry.source_file},
                    )
                    if not compressed or len(compressed) >= len(entry.content):
                        continue

                    if not dry_run:
                        tool_update_drawer(drawer_id, content=compressed)
                    report.entries_compressed += 1
    except Exception as exc:
        _log.exception("stage/compress failed")
        report.errors.append(f"compress: {exc}")


# ── Stage 7: Index rebuild (deep only) ──────────────────────────


def _stage_rebuild(report: OptimizeReport, dry_run: bool) -> None:
    """Rebuild HNSW index to reclaim space from deletes."""
    from core.palace import rebuild_index

    if dry_run:
        return

    try:
        rebuild_index()
        report.index_rebuilt = True
    except Exception as exc:
        _log.exception("stage/rebuild failed")
        report.errors.append(f"rebuild: {exc}")


# ── Stage 8: Migration check (deep only) ────────────────────────


def _stage_migration(report: OptimizeReport, dry_run: bool) -> None:
    """Check and optionally run ChromaDB version migration."""
    from core.palace import check_migration_needed, run_migration

    try:
        info = check_migration_needed()
        report.migration_needed = info["needed"]

        if info["needed"] and not dry_run:
            report.migration_done = run_migration(dry_run=False)
    except Exception as exc:
        _log.exception("stage/migration failed")
        report.errors.append(f"migration: {exc}")


# ── Stage 9: Cache clear (deep only) ────────────────────────────


def _stage_cache_clear(report: OptimizeReport, dry_run: bool) -> None:
    """Clear ChromaDB internal cache after heavy operations."""
    from core.palace import clear_cache

    if dry_run:
        return

    try:
        clear_cache()
    except Exception as exc:
        _log.exception("stage/cache_clear failed")
        report.errors.append(f"cache_clear: {exc}")
