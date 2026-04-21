"""
RAG retrieval chain (v1.0).
Searches the MemPalace and returns ranked results with confidence scores.
"""

from dataclasses import dataclass

from core.palace import search as _palace_search


@dataclass
class RetrievalResult:
    """A single retrieval result with metadata and relevance score."""
    content: str
    collection: str
    entry_id: str
    relevance_score: float
    metadata: dict


def search_memory(
    query: str,
    top_k: int = 5,
    wing: str | None = None,
    room: str | None = None,
) -> list[RetrievalResult]:
    """
    Search the palace for relevant entries.

    Args:
        query: Natural-language question.
        top_k: Max results to return overall.
        wing: Optional wing filter.
        room: Optional room filter.

    Returns:
        List of RetrievalResult sorted by relevance (best first).
    """
    hits = _palace_search(query, wing=wing, room=room, top_k=top_k)

    results: list[RetrievalResult] = []
    for hit in hits:
        results.append(RetrievalResult(
            content=hit.content,
            collection=f"{hit.wing}-{hit.room}",
            entry_id=hit.metadata.get("entry_id", ""),
            relevance_score=hit.similarity,
            metadata=hit.metadata,
        ))

    results.sort(key=lambda r: r.relevance_score, reverse=True)
    return results[:top_k]
