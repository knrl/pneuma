"""
MCP Tools: Diary — agent journal for observations and session notes.
"""

from core.palace import diary_write as _write, diary_read as _read


async def write_diary(
    entry: str,
    topic: str = "general",
    agent_name: str = "copilot",
) -> str:
    """Write a diary entry — the agent's personal journal.
    Use at session end or when you learn something worth remembering.
    Keep entries brief (1-3 sentences) to prevent memory inflation.

    Args:
        entry: What to record — focus on what changed, what was decided,
               or what to remember next time. Keep it short.
        topic: Category (default "general"). Examples: "debugging",
               "deployment", "architecture", "review".
        agent_name: Name of the agent writing (default "copilot").
    """
    result = _write(agent_name=agent_name, entry=entry, topic=topic)

    if result.get("success"):
        return (
            f"Diary entry saved (topic: {topic})\n"
            f"ID: {result.get('entry_id', '?')}\n"
            f"Time: {result.get('timestamp', '?')}"
        )
    return f"Failed to write diary entry: {result.get('error', 'unknown error')}"


async def read_diary(
    agent_name: str = "copilot",
    limit: int = 5,
) -> str:
    """Read recent diary entries — the agent's personal journal.
    Use at session start to recall what happened in previous sessions.

    Args:
        agent_name: Name of the agent whose diary to read (default "copilot").
        limit: How many recent entries to return (default 5).
    """
    result = _read(agent_name=agent_name, last_n=limit)

    entries = result.get("entries", [])
    if not entries:
        return f"No diary entries for '{agent_name}' yet."

    total = result.get("total", len(entries))
    showing = result.get("showing", len(entries))

    lines = [f"Diary for '{agent_name}' (showing {showing} of {total}):\n"]
    for e in entries:
        date = e.get("date", "?")
        topic = e.get("topic", "general")
        content = e.get("content", "")
        lines.append(f"  [{date}] ({topic})")
        for line in content.strip().split("\n"):
            lines.append(f"    {line}")
        lines.append("")

    return "\n".join(lines)
