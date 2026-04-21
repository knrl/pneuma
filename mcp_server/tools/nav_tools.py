"""
MCP Tools: Navigation — explore palace structure, find cross-wing bridges.

Consolidated tool surface (2 tools):
  explore_palace  — walk the palace graph from a room
  find_bridges    — find rooms that bridge two wings
"""

from core.palace import traverse_palace, find_palace_tunnels


async def explore_palace(start_room: str, max_hops: int = 2) -> str:
    """Walk the palace graph starting from a room to discover connected rooms.
    Use to understand how topics relate across different knowledge domains.

    Args:
        start_room: Room name to start from (e.g. "api", "architecture").
        max_hops: How many hops to traverse (default 2, max 5).
    """
    max_hops = min(max_hops, 5)
    results = traverse_palace(start_room, max_hops=max_hops)

    if not results or isinstance(results, dict):
        error_msg = ""
        if isinstance(results, dict) and results.get("error"):
            error_msg = f" ({results['error']})"
        return f"No connections found from room '{start_room}'.{error_msg}"

    lines = [f"Graph traversal from '{start_room}' (max {max_hops} hops):\n"]
    for node in results:
        hop = node.get("hop", 0)
        room = node.get("room", "?")
        wings = ", ".join(node.get("wings", []))
        count = node.get("count", 0)
        lines.append(f"  [hop {hop}] {room} — wings: {wings} ({count} entries)")

    return "\n".join(lines)


async def find_bridges(
    wing_a: str = "",
    wing_b: str = "",
) -> str:
    """Find rooms that bridge two wings — topics spanning multiple knowledge domains.
    Use to discover how different areas of knowledge overlap.

    Args:
        wing_a: First wing filter (optional).
        wing_b: Second wing filter (optional).
               Leave both empty to find all cross-wing bridges.
    """
    results = find_palace_tunnels(
        wing_a=wing_a or None,
        wing_b=wing_b or None,
    )

    if not results:
        filters = []
        if wing_a:
            filters.append(wing_a)
        if wing_b:
            filters.append(wing_b)
        filter_str = " between " + " and ".join(filters) if filters else ""
        return f"No cross-wing connections found{filter_str}."

    lines = [f"Cross-wing connections ({len(results)} tunnels):\n"]
    for tunnel in results:
        room = tunnel.get("room", "?")
        wings = ", ".join(tunnel.get("wings", []))
        count = tunnel.get("count", 0)
        lines.append(f"  {room} — bridges: {wings} ({count} entries)")

    return "\n".join(lines)
