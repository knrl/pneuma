"""
Ingestion pipeline (v1.0).
Accepts arbitrary content + metadata, routes it to the correct
MemPalace wing/room via the auto-organization router, and stores it.
"""

import time

from core.auto_org.router import route
from core.palace import add_entry


def inject_entry(
    content: str,
    metadata: dict | None = None,
    entry_id: str | None = None,
) -> dict:
    """
    Ingest a single piece of content into the palace.

    1. Route the content to the appropriate wing/room.
    2. Store via the palace adapter (mempalace).

    Args:
        content: Text to store (chat message, code snippet, decision, etc.).
        metadata: Optional dict of extra metadata fields.
        entry_id: Optional explicit ID; auto-generated if omitted.

    Returns:
        Summary dict with ``entry_id``, ``collection``, and ``ingested_at``.
    """
    metadata = dict(metadata) if metadata else {}

    wing, room = route(content, metadata)

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
    }


def inject_batch(
    entries: list[dict],
    batch_size: int = 50,
) -> dict:
    """
    Ingest multiple entries.  Each dict must have a ``content`` key;
    optional ``metadata`` and ``id`` keys.

    Returns a summary with counts.
    """
    start = time.time()
    stored = 0
    errors: list[str] = []

    for entry in entries:
        try:
            inject_entry(
                content=entry["content"],
                metadata=entry.get("metadata"),
                entry_id=entry.get("id"),
            )
            stored += 1
        except Exception as exc:
            errors.append(str(exc))

    return {
        "stored": stored,
        "errors": errors,
        "elapsed_seconds": round(time.time() - start, 2),
    }
