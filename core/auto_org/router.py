"""
Content router — classifies incoming content and returns
the target (wing, room) pair for storage in the MemPalace.

Uses keyword heuristics. For MCP tool calls the AI agent can
specify the target directly via metadata["wing"] / metadata["room"].
"""

# ── Keyword rules (checked in order; first match wins) ──────────

_KEYWORD_RULES: list[tuple[list[str], tuple[str, str]]] = [
    # Escalations
    (["escalate", "help needed", "blocked", "stuck", "can't figure"], ("chat", "escalations")),
    # Decisions / architecture
    (["decided", "decision", "we agreed", "convention", "standard", "architecture"], ("chat", "decisions")),
    (["style guide", "naming convention", "lint", "format"], ("chat", "conventions")),
    # Chat knowledge
    (["workaround", "hack", "temp fix", "temporary", "hotfix"], ("chat", "workarounds")),
    (["solution", "solved", "fixed", "answer", "resolved"], ("chat", "solutions")),
]

_DEFAULT_WING_ROOM = ("chat", "context")


def route(content: str, metadata: dict | None = None) -> tuple[str, str]:
    """
    Return the best ``(wing, room)`` pair for *content*.

    1. If metadata already contains ``wing`` and ``room``, honour them.
    2. Try keyword rules against the lowered content.
    3. Fall back to the default wing/room.
    """
    if metadata and metadata.get("wing") and metadata.get("room"):
        return (metadata["wing"], metadata["room"])

    target = _keyword_match(content)
    if target:
        return target

    return _DEFAULT_WING_ROOM


def _keyword_match(content: str) -> tuple[str, str] | None:
    text = content.lower()
    for keywords, wing_room in _KEYWORD_RULES:
        if any(kw in text for kw in keywords):
            return wing_room
    return None
