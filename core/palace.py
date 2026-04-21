"""
Central adapter — every Pneuma module talks to MemPalace through here.
No other file should import chromadb or mempalace directly.
"""

import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass

_log = logging.getLogger("pneuma.palace")

from mempalace.config import MempalaceConfig
from mempalace.knowledge_graph import KnowledgeGraph
from mempalace.layers import MemoryStack, Layer3
from mempalace.searcher import search_memories

# mempalace.mcp_server redirects fd 1 → stderr at import time via
# os.dup2(2, 1) to protect its own MCP stdio transport from noisy
# C-level output.  We only need the tool helper functions, so save
# the real fd 1 and restore it after import.
_saved_stdout = sys.stdout
_saved_fd = os.dup(1)
from mempalace.mcp_server import (
    tool_add_drawer,
    tool_check_duplicate,
    tool_delete_drawer,
    tool_diary_write,
    tool_diary_read,
    tool_list_wings,
    tool_list_rooms,
    tool_get_taxonomy,
    tool_status,
    tool_traverse_graph,
    tool_find_tunnels,
    tool_graph_stats,
    tool_kg_stats,
    tool_get_aaak_spec,
)
import mempalace.mcp_server as _mp_mcp
os.dup2(_saved_fd, 1)
os.close(_saved_fd)
sys.stdout = _saved_stdout

# ── Singletons ───────────────────────────────────────────────────

_config: MempalaceConfig | None = None
_stack: MemoryStack | None = None
_kg: KnowledgeGraph | None = None
_active_project: dict | None = None  # set by configure()


def configure(project_path: str | None = None) -> dict | None:
    """
    Configure palace to use a specific project's isolated data directory.
    Must be called before any palace operations when multi-project support
    is needed.  Sets MEMPALACE_PALACE_PATH so mempalace resolves correctly.

    Args:
        project_path: Explicit project path. If None, auto-detects from CWD.

    Returns:
        Project info dict, or None if no project is registered.
    """
    global _config, _stack, _kg, _active_project
    from core.registry import resolve_project, get_project

    proj = None
    if project_path:
        proj = get_project(project_path)
    if not proj:
        proj = resolve_project()
    if not proj:
        return None

    # Set env var BEFORE creating MempalaceConfig — mempalace reads it
    os.environ["MEMPALACE_PALACE_PATH"] = proj["palace_path"]

    # Also redirect mempalace.mcp_server's module-level _config
    _mp_mcp._config = MempalaceConfig()
    _mp_mcp._client_cache = None
    _mp_mcp._collection_cache = None

    # Reset singletons so they pick up new paths
    _config = None
    _stack = None
    _kg = None
    _active_project = proj
    return proj


def _get_config() -> MempalaceConfig:
    global _config
    if _config is None:
        _config = MempalaceConfig()
    return _config


def get_stack() -> MemoryStack:
    """Return a singleton MemoryStack."""
    global _stack
    if _stack is None:
        _stack = MemoryStack(palace_path=_get_config().palace_path)
    return _stack


def get_kg() -> KnowledgeGraph:
    """Return a singleton KnowledgeGraph."""
    global _kg
    if _kg is None:
        kg_path = None
        if _active_project:
            kg_path = _active_project["kg_path"]
        _kg = KnowledgeGraph(db_path=kg_path)
    return _kg


def palace_path() -> str:
    """Return the configured palace path."""
    return _get_config().palace_path


# ── Write ────────────────────────────────────────────────────────

def add_entry(
    wing: str,
    room: str,
    content: str,
    metadata: dict | None = None,
    entry_id: str | None = None,
    source: str = "pneuma",
) -> dict:
    """
    Add a drawer to the palace via mempalace's tool_add_drawer.

    Returns dict with ``entry_id``, ``wing``, ``room``, ``ingested_at``.
    """
    result = tool_add_drawer(
        wing=wing,
        room=room,
        content=content,
        source_file=(metadata or {}).get("source_file"),
        added_by=source,
    )

    # tool_add_drawer returns {"success": True, "drawer_id": ..., "wing": ..., "room": ...}
    # or {"success": False, "reason": "duplicate", ...}
    now = time.time()
    return {
        "entry_id": result.get("drawer_id", entry_id or f"pneuma-{uuid.uuid4().hex[:12]}"),
        "wing": wing,
        "room": room,
        "collection": f"{wing}-{room}",
        "ingested_at": now,
        "duplicate": not result.get("success", True) and result.get("reason") == "duplicate",
    }


def delete_entry(drawer_id: str) -> dict:
    """Delete a drawer by ID."""
    return tool_delete_drawer(drawer_id)


# ── Wake-up / Recall ─────────────────────────────────────────────

def wake_up(wing: str | None = None) -> str:
    """L0 identity + L1 essential story.  ~600-900 tokens for system prompt."""
    return get_stack().wake_up(wing=wing)


def recall(wing: str | None = None, room: str | None = None, n_results: int = 10) -> str:
    """L2 on-demand retrieval filtered by wing/room."""
    return get_stack().recall(wing=wing, room=room, n_results=n_results)


# ── Read / Search ────────────────────────────────────────────────

@dataclass
class SearchResult:
    """A single search hit from the palace."""
    content: str
    wing: str
    room: str
    similarity: float
    source_file: str
    metadata: dict


def search(
    query: str,
    wing: str | None = None,
    room: str | None = None,
    top_k: int = 5,
) -> list[SearchResult]:
    """
    Semantic search across the palace.
    Optionally filter by wing and/or room.
    """
    raw = search_memories(
        query,
        palace_path=_get_config().palace_path,
        wing=wing,
        room=room,
        n_results=top_k,
    )

    if not raw or "error" in raw:
        return []

    results: list[SearchResult] = []
    for hit in raw.get("results", []):
        results.append(SearchResult(
            content=hit["text"],
            wing=hit.get("wing", "unknown"),
            room=hit.get("room", "unknown"),
            similarity=hit.get("similarity", 0.0),
            source_file=hit.get("source_file", ""),
            metadata=hit,
        ))

    # Bump retrieval_count for returned entries so the stale-entry
    # detector in refactor.py can distinguish used vs. unused knowledge.
    if results:
        _bump_retrieval_counts(results)

    return results


def _bump_retrieval_counts(results: list[SearchResult]) -> None:
    """Increment ``retrieval_count`` metadata for each returned search hit.

    MemPalace / ChromaDB do not track retrieval frequency automatically.
    This counter is available for future heuristics (e.g. weighted stale
    detection). Best-effort: failures are logged but never raised.
    """
    col = _mp_mcp._get_collection()
    if not col:
        return

    # The search results from mempalace don't carry ChromaDB IDs.
    # We re-query the collection for each result's source_file to
    # find matching IDs.  This is lightweight: small where-filter
    # queries are fast in ChromaDB and we only update a few IDs.
    source_files = {
        r.source_file for r in results if r.source_file and r.source_file != "?"
    }

    if not source_files:
        return

    for source_file in source_files:
        try:
            matched = col.get(
                where={"source_file": source_file},
                include=["metadatas"],
                limit=200,
            )
            matched_ids = matched.get("ids", []) if isinstance(matched, dict) else []
            matched_metas = matched.get("metadatas", []) if isinstance(matched, dict) else []

            if not matched_ids:
                continue

            updated_metas = []
            for meta in matched_metas:
                count = 0
                try:
                    count = int(meta.get("retrieval_count", 0))
                except (TypeError, ValueError):
                    pass
                new_meta = dict(meta)
                new_meta["retrieval_count"] = count + 1
                updated_metas.append(new_meta)

            col.update(ids=matched_ids, metadatas=updated_metas)
        except Exception:
            _log.debug("retrieval_count bump failed for '%s'", source_file, exc_info=True)


def check_duplicate(content: str, threshold: float = 0.9) -> dict:
    """Check whether similar content already exists."""
    return tool_check_duplicate(content, threshold=threshold)


# ── Listing ──────────────────────────────────────────────────────

def list_wings() -> dict[str, int]:
    """Return {wing_name: drawer_count}."""
    result = tool_list_wings()
    return result.get("wings", {})


def list_rooms(wing: str | None = None) -> dict[str, int]:
    """Return {room_name: drawer_count}, optionally filtered by wing."""
    result = tool_list_rooms(wing=wing)
    return result.get("rooms", {})


def get_taxonomy() -> dict[str, dict[str, int]]:
    """Return {wing: {room: count}} — full structure."""
    result = tool_get_taxonomy()
    return result.get("taxonomy", {})


def status() -> dict:
    """Palace status — drawer count, wing/room breakdown, path."""
    return tool_status()


def list_room_entries(wing: str, room: str) -> list[SearchResult]:
    """
    Return every entry in wing/room via metadata filter — no vector search.
    Guaranteed full coverage regardless of room size. Use for bulk operations
    (deduplication, stale scan) where search("*") would miss entries.
    """
    from mempalace.palace import get_collection as _mp_get_collection

    try:
        col = _mp_get_collection(_get_config().palace_path, create=False)
    except Exception:
        return []

    where = {"$and": [{"wing": {"$eq": wing}}, {"room": {"$eq": room}}]}
    try:
        result = col.get(where=where, include=["documents", "metadatas"])
    except Exception:
        return []

    ids = result.get("ids") or []
    docs = result.get("documents") or []
    metas = result.get("metadatas") or []

    entries = []
    for entry_id, doc, meta in zip(ids, docs, metas):
        meta = dict(meta) if meta else {}
        meta["id"] = entry_id
        entries.append(SearchResult(
            content=doc or "",
            wing=meta.get("wing", wing),
            room=meta.get("room", room),
            similarity=0.0,
            source_file=meta.get("source_file", ""),
            metadata=meta,
        ))
    return entries


# ── Navigation ───────────────────────────────────────────────────

def traverse_palace(start_room: str, max_hops: int = 2) -> list:
    """Walk the palace graph from a room."""
    return tool_traverse_graph(start_room, max_hops=max_hops)


def find_palace_tunnels(wing_a: str | None = None, wing_b: str | None = None) -> list:
    """Find rooms that bridge two wings."""
    return tool_find_tunnels(wing_a, wing_b)


def palace_graph_stats() -> dict:
    """Palace graph overview."""
    return tool_graph_stats()


def kg_stats() -> dict:
    """Knowledge graph stats: entities, triples, relationship types."""
    return tool_kg_stats()


def aaak_spec() -> dict:
    """Return the AAAK dialect specification."""
    return tool_get_aaak_spec()


# ── Diary ────────────────────────────────────────────────────────

DIARY_MAX_ENTRIES = 200

_diary_max = os.getenv("DIARY_MAX_ENTRIES")
if _diary_max:
    DIARY_MAX_ENTRIES = int(_diary_max)


def diary_write(agent_name: str, entry: str, topic: str = "general") -> dict:
    """Write a diary entry for an agent, then prune oldest beyond the cap."""
    result = tool_diary_write(agent_name=agent_name, entry=entry, topic=topic)
    if result.get("success"):
        _prune_diary(agent_name)
    return result


def diary_read(agent_name: str, last_n: int = 10) -> dict:
    """Read recent diary entries for an agent."""
    return tool_diary_read(agent_name=agent_name, last_n=last_n)


def _prune_diary(agent_name: str) -> int:
    """Delete the oldest diary entries beyond DIARY_MAX_ENTRIES.

    Returns the number of entries pruned.
    """
    col = _mp_mcp._get_collection()
    if not col:
        return 0

    wing = f"wing_{agent_name.lower().replace(' ', '_')}"
    try:
        results = col.get(
            where={"$and": [{"wing": wing}, {"room": "diary"}]},
            include=["metadatas"],
            limit=10000,
        )
    except Exception:
        return 0

    ids = results.get("ids", []) if isinstance(results, dict) else (results["ids"] if results else [])
    metadatas = results.get("metadatas", []) if isinstance(results, dict) else (results["metadatas"] if results else [])

    if not ids or len(ids) <= DIARY_MAX_ENTRIES:
        return 0

    # Sort by filed_at ascending (oldest first)
    entries = list(zip(ids, metadatas))
    entries.sort(key=lambda e: e[1].get("filed_at", ""))

    to_delete = [eid for eid, _ in entries[: len(entries) - DIARY_MAX_ENTRIES]]
    if not to_delete:
        return 0

    try:
        col.delete(ids=to_delete)
        _log.info("Pruned %d old diary entries for agent '%s'", len(to_delete), agent_name)
    except Exception:
        _log.exception("Failed to prune diary for agent '%s'", agent_name)
        return 0

    return len(to_delete)


# ── Init ─────────────────────────────────────────────────────────

def init_palace(wings: list[dict] | None = None) -> list[str]:
    """
    Seed placeholder drawers so wings/rooms appear in listings.

    Args:
        wings: List of {"name": str, "rooms": [{"name": str, "description": str}]}

    Returns:
        List of room names provisioned.
    """
    provisioned: list[str] = []

    if not wings:
        return provisioned

    for wing_def in wings:
        wing_name = wing_def["name"]
        for room_def in wing_def["rooms"]:
            room_name = room_def["name"]
            description = room_def.get("description", f"{wing_name}/{room_name}")
            # tool_add_drawer checks duplicates internally
            tool_add_drawer(
                wing=wing_name,
                room=room_name,
                content=description,
                source_file="",
                added_by="pneuma-init",
            )
            provisioned.append(room_name)

    return provisioned


# ── Optimization adapters ────────────────────────────────────────

def batch_dedup(
    threshold: float = 0.08,
    dry_run: bool = True,
    wing: str | None = None,
    source_pattern: str | None = None,
) -> dict:
    """
    Batch near-duplicate removal using mempalace's embedding dedup.

    Args:
        threshold: Cosine *distance* (0.08 ≈ 0.92 similarity).
        dry_run: If True, report only.
        wing: Scope to a single wing.
        source_pattern: Filter by source_file substring.

    Returns:
        {"kept": int, "deleted": int, "groups_checked": int,
         "details": [{"source": str, "kept": [str], "deleted": [str]}]}
    """
    from mempalace.dedup import get_source_groups, dedup_source_group
    from mempalace.palace import get_collection as _mp_get_collection

    col = _mp_get_collection(_get_config().palace_path, create=False)
    groups = get_source_groups(
        col, min_count=2, source_pattern=source_pattern, wing=wing,
    )

    total_kept = 0
    total_deleted = 0
    details: list[dict] = []

    for source, ids in groups.items():
        kept, deleted = dedup_source_group(
            col, ids, threshold=threshold, dry_run=dry_run,
        )
        total_kept += len(kept)
        total_deleted += len(deleted)
        if deleted:
            details.append({
                "source": source,
                "kept": kept,
                "deleted": deleted,
            })

    return {
        "kept": total_kept,
        "deleted": total_deleted,
        "groups_checked": len(groups),
        "details": details,
    }


def cross_source_dedup(
    threshold: float = 0.08,
    dry_run: bool = True,
) -> dict:
    """
    Cross-source near-duplicate removal — catches duplicates that the
    per-source ``batch_dedup`` misses because the entries have different
    ``source_file`` values (e.g., Slack ingestion vs manual save).

    Feeds ALL drawer IDs into a single dedup group so every entry is
    compared against every other regardless of source or wing/room.

    Args:
        threshold: Cosine *distance* (0.08 ≈ 0.92 similarity).
        dry_run: If True, report only.

    Returns:
        {"kept": int, "deleted": int,
         "details": [{"source": "cross-source", "kept": [str], "deleted": [str]}]}
    """
    from mempalace.dedup import dedup_source_group
    from mempalace.palace import get_collection as _mp_get_collection

    col = _mp_get_collection(_get_config().palace_path, create=False)
    total = col.count()
    if total < 2:
        return {"kept": 0, "deleted": 0, "details": []}

    # Collect ALL drawer IDs in batches
    all_ids: list[str] = []
    offset = 0
    batch_size = 1000
    while offset < total:
        batch = col.get(limit=batch_size, offset=offset, include=[])
        if not batch["ids"]:
            break
        all_ids.extend(batch["ids"])
        offset += len(batch["ids"])

    if len(all_ids) < 2:
        return {"kept": 0, "deleted": 0, "details": []}

    kept, deleted = dedup_source_group(
        col, all_ids, threshold=threshold, dry_run=dry_run,
    )

    details = []
    if deleted:
        details.append({
            "source": "cross-source",
            "kept": kept,
            "deleted": deleted,
        })

    return {
        "kept": len(kept),
        "deleted": len(deleted),
        "details": details,
    }


def scan_index(wing: str | None = None) -> dict:
    """
    Scan HNSW index for corrupt/unfetchable IDs.

    Returns:
        {"good": int, "bad": int, "bad_ids": list[str]}
    """
    from mempalace.repair import scan_palace
    good_set, bad_set = scan_palace(
        palace_path=_get_config().palace_path, only_wing=wing,
    )
    return {"good": len(good_set), "bad": len(bad_set), "bad_ids": list(bad_set)}


def prune_corrupt_ids(bad_ids: list[str]) -> int:
    """
    Delete corrupt IDs directly (bypasses corrupt_ids.txt dependency).

    Returns:
        Number of IDs pruned.
    """
    if not bad_ids:
        return 0
    from mempalace.palace import get_collection as _mp_get_collection

    col = _mp_get_collection(_get_config().palace_path, create=False)
    col.delete(ids=bad_ids)
    return len(bad_ids)


def rebuild_index() -> None:
    """
    Rebuild HNSW index from scratch: extract → drop → recreate → upsert.
    Reclaims space from accumulated deletes.
    """
    from mempalace.repair import rebuild_index as _rebuild
    _rebuild(palace_path=_get_config().palace_path)


def compress_entry(content: str, metadata: dict | None = None) -> str:
    """
    Compress text into AAAK dialect format (rule-based, no LLM).

    Returns:
        AAAK-formatted string.
    """
    from mempalace.dialect import Dialect
    return Dialect().compress(content, metadata=metadata)


def check_facts(text: str) -> list[dict]:
    """
    Check text for contradictions against the knowledge graph.

    Returns:
        List of issue dicts (empty = no contradictions).
    """
    from mempalace.fact_checker import check_text
    return check_text(text, palace_path=_get_config().palace_path)


def get_indexing_status() -> dict:
    """
    Query ChromaDB indexing progress.

    Returns:
        {"indexed": int, "unindexed": int, "progress": float}
    """
    from mempalace.palace import get_collection as _mp_get_collection

    col = _mp_get_collection(_get_config().palace_path, create=False)
    status = col.get_indexing_status()
    return {
        "indexed": status.num_indexed_ops,
        "unindexed": status.num_unindexed_ops,
        "progress": status.op_indexing_progress,
    }


def clear_cache() -> None:
    """Clear ChromaDB internal cache."""
    client = _mp_mcp._get_client()
    if client and hasattr(client, "clear_system_cache"):
        client.clear_system_cache()


def check_migration_needed() -> dict:
    """
    Check if ChromaDB version migration is needed.

    Returns:
        {"db_version": str, "current_version": str, "needed": bool}
    """
    import chromadb
    from mempalace.migrate import detect_chromadb_version

    pp = _get_config().palace_path
    db_path = os.path.join(pp, "chroma.sqlite3")
    db_ver = detect_chromadb_version(db_path) if os.path.exists(db_path) else "unknown"
    cur_ver = chromadb.__version__
    # Major version mismatch means migration needed
    needed = db_ver != "unknown" and not cur_ver.startswith(db_ver.rstrip(".x"))
    return {"db_version": db_ver, "current_version": cur_ver, "needed": needed}


def run_migration(dry_run: bool = False) -> bool:
    """
    Run ChromaDB version migration.

    Returns:
        True on success.
    """
    from mempalace.migrate import migrate
    return migrate(_get_config().palace_path, dry_run=dry_run, confirm=True)
