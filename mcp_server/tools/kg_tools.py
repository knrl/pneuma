"""
MCP Tools: Knowledge Graph — track facts, query relationships,
manage temporal validity.

Consolidated tool surface (3 tools):
  track_fact       — record a temporal fact/relationship
  query_facts      — look up entity relationships (+ optional timeline)
  invalidate_fact  — mark a fact as expired

(KG summary stats are available via palace_overview(detail="full").)
"""

from core.palace import get_kg


async def track_fact(
    subject: str,
    predicate: str,
    value: str,
    valid_from: str = "",
    confidence: float = 1.0,
) -> str:
    """Record a temporal fact (relationship) in the knowledge graph.
    Use to track decisions, team assignments, technology choices, or any
    evolving truth. Facts can be invalidated later when they change.

    Args:
        subject: The entity the fact is about (e.g. "Auth Service").
        predicate: The relationship type (e.g. "uses", "assigned_to",
                   "decided", "migrated_to").
        value: The target entity (e.g. "JWT", "Alice", "PostgreSQL").
        valid_from: When this fact became true (ISO date, e.g. "2026-01-15").
                    Leave empty for "now".
        confidence: How confident we are in this fact (0.0–1.0, default 1.0).
    """
    kg = get_kg()
    triple_id = kg.add_triple(
        subject=subject,
        predicate=predicate,
        obj=value,
        valid_from=valid_from or None,
        confidence=confidence,
    )
    return (
        f"Fact recorded: {subject} → {predicate} → {value}\n"
        f"Triple ID: {triple_id}"
    )


async def query_facts(
    entity: str,
    as_of: str = "",
    direction: str = "both",
    chronological: bool = False,
) -> str:
    """Look up all relationships for an entity in the knowledge graph.
    Use when you need to understand what's known about a person, service,
    technology, or concept. Returns incoming and outgoing relationships.

    Args:
        entity: The entity to look up (e.g. "Auth Service", "Alice").
        as_of: Optional date filter (ISO format). Returns only facts
               valid at that time. Leave empty for current facts.
        direction: "outgoing", "incoming", or "both" (default "both").
        chronological: If true, return a timeline view showing when facts
                       were established and expired. Useful for understanding
                       how knowledge evolved over time.
    """
    kg = get_kg()

    if chronological:
        return _format_timeline(kg, entity)

    facts = kg.query_entity(
        name=entity,
        as_of=as_of or None,
        direction=direction,
    )

    if not facts:
        return f"No facts found for '{entity}'."

    lines = [f"Facts about '{entity}' ({len(facts)} total):\n"]
    for f in facts:
        direction_marker = "→" if f.get("direction") == "outgoing" else "←"
        current = "✓" if f.get("current") else "✗"
        lines.append(
            f"  [{current}] {f.get('subject', '?')} {direction_marker} "
            f"{f.get('predicate', '?')} {direction_marker} {f.get('object', '?')}"
        )
        if f.get("valid_from"):
            lines.append(f"      valid: {f['valid_from']} → {f.get('valid_to', 'present')}")

    return "\n".join(lines)


def _format_timeline(kg, entity: str) -> str:
    """Format facts as a chronological timeline."""
    timeline = kg.timeline(entity_name=entity or None)

    if not timeline:
        return f"No timeline data{' for ' + entity if entity else ''}."

    lines = [f"Timeline{' for ' + entity if entity else ''} ({len(timeline)} facts):\n"]
    for entry in timeline:
        status = "current" if entry.get("current") else "expired"
        valid_to = entry.get("valid_to", "present")
        lines.append(
            f"  [{status}] {entry.get('subject', '?')} → "
            f"{entry.get('predicate', '?')} → {entry.get('object', '?')}"
        )
        lines.append(
            f"      {entry.get('valid_from', '?')} → {valid_to}"
        )

    return "\n".join(lines)


async def invalidate_fact(
    subject: str,
    predicate: str,
    value: str,
    ended: str = "",
) -> str:
    """Mark a fact as no longer true. The fact stays in history with an end date.
    Use when a decision changes, someone leaves, or a technology is replaced.

    Args:
        subject: The subject entity.
        predicate: The relationship type.
        value: The target entity.
        ended: When the fact stopped being true (ISO date).
               Leave empty for "today".
    """
    kg = get_kg()
    kg.invalidate(
        subject=subject,
        predicate=predicate,
        obj=value,
        ended=ended or None,
    )
    return (
        f"Invalidated: {subject} → {predicate} → {value}\n"
        f"Ended: {ended or 'today'}"
    )


