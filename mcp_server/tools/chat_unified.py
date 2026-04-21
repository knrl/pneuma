"""
MCP Tools: Chat (platform-agnostic) — Slack and Microsoft Teams behind
a single tool surface.

Each tool takes an optional ``platform`` parameter. When ``platform="auto"``
we pick whichever backend is configured (Slack preferred if both are set).
When a specific platform is named, we require its credentials.

These wrappers delegate to the existing platform-specific modules —
chat_tools, slack_ingest_tools, teams_chat_tools, teams_ingest_tools,
and escalation — without duplicating any backend logic.
"""

import os


# ── Platform resolution ──────────────────────────────────────────────────────

def _slack_available() -> bool:
    return bool(os.getenv("SLACK_BOT_TOKEN", ""))


def _teams_available() -> bool:
    return bool(os.getenv("TEAMS_CLIENT_ID", ""))


def _resolve_platform(platform: str) -> tuple[str, str]:
    """
    Return (resolved_platform, error_msg). If error_msg is non-empty,
    the caller should return it directly.
    """
    p = (platform or "auto").lower().strip()

    if p == "auto":
        if _slack_available():
            return ("slack", "")
        if _teams_available():
            return ("teams", "")
        return ("", (
            "No chat platform is configured. Set SLACK_BOT_TOKEN or "
            "TEAMS_CLIENT_ID (and friends) in your .env file."
        ))

    if p == "slack":
        if _slack_available():
            return ("slack", "")
        return ("", "Slack is not configured. Set SLACK_BOT_TOKEN in .env.")

    if p == "teams":
        if _teams_available():
            return ("teams", "")
        return ("", "Microsoft Teams is not configured. Set TEAMS_CLIENT_ID in .env.")

    return ("", f"Unknown platform '{platform}'. Use 'slack', 'teams', or 'auto'.")


# ── Public tools ─────────────────────────────────────────────────────────────

async def check_recent_chat(
    topic: str,
    count: int = 10,
    platform: str = "auto",
) -> str:
    """Search recent chat messages for a topic across the configured platform.
    Use before searching the knowledge base to catch discussions that haven't
    been ingested yet.

    Args:
        topic: Keyword or phrase to search for.
        count: Maximum messages to return (default 10, max 20).
        platform: "slack" | "teams" | "auto" (picks whichever is configured,
                  Slack preferred if both).
    """
    p, err = _resolve_platform(platform)
    if err:
        return err

    if p == "slack":
        from mcp_server.tools.chat_tools import check_recent_chat as _fn
        return await _fn(topic, count)

    from mcp_server.tools.teams_chat_tools import check_recent_teams_chat as _fn
    return await _fn(topic, count)


async def ask_team(
    question: str,
    target: str = "",
    platform: str = "auto",
) -> str:
    """Post a question to a chat channel on behalf of the AI assistant.
    Use when you need real-time human input not found in the knowledge base.

    Args:
        question: The question to post.
        target: Channel ID (Slack) or webhook URL (Teams).
                Leave empty to use SLACK_DEFAULT_CHANNEL / TEAMS_DEFAULT_WEBHOOK_URL.
        platform: "slack" | "teams" | "auto".
    """
    p, err = _resolve_platform(platform)
    if err:
        return err

    if p == "slack":
        from mcp_server.tools.chat_tools import ask_team as _fn
        return await _fn(question, target)

    # Teams treats `target` as the webhook URL
    from mcp_server.tools.teams_chat_tools import ask_teams_channel as _fn
    return await _fn(question, target)


async def ingest_chat_channel(
    channel: str,
    platform: str,
    hours_back: float = 24.0,
    limit: int = 200,
    team_id: str = "",
) -> str:
    """Fetch recent messages from a chat channel and store extracted knowledge.
    Messages are noise-filtered, anonymized, and extracted into problem/solution
    stories before being stored in the palace.

    Args:
        channel: Channel identifier. For Slack: channel ID like "C0123ABCDEF".
                 For Teams: channel ID from the channel URL.
        platform: "slack" or "teams" — required (auto-detection is unsafe here
                  because channel ID formats differ).
        hours_back: Hours of history to fetch (default 24). Use 168 for a week.
        limit: Max messages to fetch before filtering (default 200).
        team_id: Teams team ID (ignored for Slack). Defaults to TEAMS_TEAM_ID.
    """
    # platform is required here — don't auto-pick
    if not platform or platform.lower() == "auto":
        return (
            "ingest_chat_channel requires an explicit platform ('slack' or 'teams'). "
            "Channel ID formats differ between platforms, so auto-detection is unsafe."
        )

    p, err = _resolve_platform(platform)
    if err:
        return err

    if p == "slack":
        from mcp_server.tools.slack_ingest_tools import ingest_slack_channel as _fn
        result = await _fn(channel, hours_back=hours_back, limit=limit)
    else:
        from mcp_server.tools.teams_ingest_tools import ingest_teams_channel as _fn
        result = await _fn(channel, team_id=team_id, hours_back=hours_back, limit=limit)

    # Bump auto-optimize counter — extract entries stored from result text
    import re
    m = re.search(r"Stories injected\s*:\s*(\d+)", result)
    if not m:
        m = re.search(r"Entries stored\s*:\s*(\d+)", result)
    if m and int(m.group(1)) > 0:
        from core.background import bump_and_maybe_optimize
        bump_and_maybe_optimize(n=int(m.group(1)))

    return result


async def escalate_to_human(
    question: str,
    code_context: str,
    platform: str = "auto",
) -> str:
    """Escalate an unanswerable question to a human expert via chat.
    Use when search_memory returns low-confidence results or no results.
    Posts to the platform's escalation channel with full code context.

    Args:
        question: The developer's original question.
        code_context: Relevant code snippet or file context (truncated to 1500 chars).
        platform: "slack" | "teams" | "auto".
    """
    p, err = _resolve_platform(platform)
    if err:
        return err

    if p == "slack":
        # Slack's internal signature is (code_context, question) — normalize here
        from mcp_server.tools.escalation import escalate_to_human as _fn
        return await _fn(code_context, question)

    from mcp_server.tools.teams_chat_tools import escalate_to_teams as _fn
    return await _fn(question, code_context)
