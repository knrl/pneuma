"""
Ingestion pipeline.
Accepts arbitrary content + metadata, routes it to the correct
MemPalace wing/room via the auto-organization router, and stores it.
"""

import os
import time

from core.auto_org.router import _route_full, load_routing_config, RoutingConfig


# ── Routing config cache ──────────────────────────────────────────────────────
# Keyed by project path so tests that switch projects get fresh configs.
# Populated lazily on first write; cleared by _invalidate_routing_cache().

_routing_cache: dict[str, RoutingConfig] = {}


def _get_routing_config() -> RoutingConfig | None:
    """Load (and cache) RoutingConfig for the active PNEUMA_PROJECT."""
    project = os.environ.get("PNEUMA_PROJECT", "").strip()
    if not project:
        return None
    if project not in _routing_cache:
        _routing_cache[project] = load_routing_config(project)
    return _routing_cache[project]


def invalidate_routing_cache(project_path: str | None = None) -> None:
    """
    Clear the routing config cache.
    Pass project_path to clear a specific project, or None to clear all.
    Useful after .pneuma.yaml is edited during a session.
    """
    if project_path:
        _routing_cache.pop(project_path, None)
    else:
        _routing_cache.clear()


# ── Pipeline ──────────────────────────────────────────────────────────────────

def inject_entry(
    content: str,
    metadata: dict | None = None,
    entry_id: str | None = None,
    routing_config: RoutingConfig | None = None,
) -> dict:
    """
    Ingest a single piece of content into the palace.

    1. Route the content to the appropriate wing/room.
    2. Store via the palace adapter (mempalace).

    Args:
        content:        Text to store.
        metadata:       Optional extra metadata fields.
        entry_id:       Optional explicit ID; auto-generated if omitted.
        routing_config: Override routing config (useful in tests or CLI).
                        Defaults to the config loaded from PNEUMA_PROJECT.

    Returns:
        Summary dict with ``entry_id``, ``collection``, and ``ingested_at``.
    """
    from core.palace import add_entry

    metadata = dict(metadata) if metadata else {}

    cfg = routing_config if routing_config is not None else _get_routing_config()
    wing, room, semantic_type = _route_full(content, metadata, config=cfg)

    if semantic_type and "semantic_type" not in metadata:
        metadata["semantic_type"] = semantic_type

    source = metadata.pop("source", "pneuma")

    result = add_entry(
        wing=wing,
        room=room,
        content=content,
        metadata=metadata,
        entry_id=entry_id,
        source=source,
    )

    return {
        "entry_id": result["entry_id"],
        "collection": result["collection"],
        "ingested_at": result["ingested_at"],
        "semantic_type": semantic_type,
    }


def inject_batch(
    entries: list[dict],
    batch_size: int = 50,
    routing_config: RoutingConfig | None = None,
) -> dict:
    """
    Ingest multiple entries.  Each dict must have a ``content`` key;
    optional ``metadata`` and ``id`` keys.

    Returns a summary with counts.
    """
    start = time.time()
    stored = 0
    errors: list[str] = []

    cfg = routing_config if routing_config is not None else _get_routing_config()

    for entry in entries:
        try:
            inject_entry(
                content=entry["content"],
                metadata=entry.get("metadata"),
                entry_id=entry.get("id"),
                routing_config=cfg,
            )
            stored += 1
        except Exception as exc:
            errors.append(str(exc))

    return {
        "stored": stored,
        "errors": errors,
        "elapsed_seconds": round(time.time() - start, 2),
    }
