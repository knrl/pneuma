"""
MCP Tools: Slack Ingestion — fetch channel history and store as knowledge.

Fetches messages from a Slack channel via the conversations.history API,
runs them through the full preprocessing pipeline (noise filter →
anonymizer → story extractor → injector), and stores the resulting
knowledge entries in mempalace.

This is the primary way to ingest Slack channel history into the
knowledge base.  Call it on-demand to backfill a channel or to
refresh knowledge before a query.
"""

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
_ALLOWED_CHANNELS: set[str] = {
    c.strip()
    for c in os.getenv("ALLOWED_CHANNELS", "").split(",")
    if c.strip()
}

# Slack API hard limit for conversations.history is 1000 messages per call.
_SLACK_MAX_LIMIT = 1000


async def ingest_slack_channel(
    channel: str,
    hours_back: float = 24.0,
    limit: int = 200,
) -> str:
    """Fetch recent messages from a Slack channel and store extracted knowledge.
    Use to backfill a channel or refresh knowledge before a query.
    Messages are noise-filtered, anonymized, and extracted into stories.

    Args:
        channel: Slack channel ID (e.g. "C0123ABCDEF"). Use the ID from
                 the channel URL, not the channel name.
        hours_back: Hours of history to pull (default 24). Use 168 for a week.
        limit: Max messages to fetch before filtering (default 200, max 1000).
    """
    if not SLACK_BOT_TOKEN:
        return (
            "Slack is not configured. "
            "Set SLACK_BOT_TOKEN in the .env file."
        )

    if _ALLOWED_CHANNELS and channel not in _ALLOWED_CHANNELS:
        return (
            f"Channel '{channel}' is not in the allowed list. "
            "Add it to ALLOWED_CHANNELS in .env to enable ingestion."
        )

    limit = min(limit, _SLACK_MAX_LIMIT)
    oldest = str(time.time() - hours_back * 3600)

    # ── 1. Fetch from Slack ──────────────────────────────────────────
    raw_messages = _fetch_history(channel, oldest=oldest, limit=limit)
    if isinstance(raw_messages, str):
        # Error string returned from _fetch_history
        return raw_messages

    fetched_count = len(raw_messages)
    if fetched_count == 0:
        return (
            f"No messages found in <#{channel}> "
            f"for the last {hours_back:.0f} h."
        )

    # ── 2. Convert to BufferedMessage ────────────────────────────────
    from chat_bot.preprocessing.noise_filter import BufferedMessage

    buffered = [
        BufferedMessage(
            user=m.get("user", "unknown"),
            text=m.get("text", ""),
            channel=channel,
            ts=m.get("ts", ""),
            thread_ts=m.get("thread_ts"),
        )
        for m in raw_messages
        # Skip bot messages, edits, and deletions
        if m.get("subtype") not in (
            "bot_message", "message_changed", "message_deleted"
        )
        and m.get("text", "").strip()
    ]

    # ── 3. Noise filter ──────────────────────────────────────────────
    from chat_bot.preprocessing.noise_filter import filter_messages

    filtered = filter_messages(buffered)
    filtered_count = len(filtered)

    if not filtered:
        return (
            f"Fetched {fetched_count} messages from <#{channel}> "
            f"but all were filtered as noise. Nothing stored."
        )

    # ── 4. Anonymize ─────────────────────────────────────────────────
    from chat_bot.preprocessing.anonymizer import anonymize_messages

    anonymized = anonymize_messages(filtered)

    # ── 5. Extract stories ───────────────────────────────────────────
    from chat_bot.preprocessing.story_extractor import extract_stories

    stories = extract_stories(anonymized)
    story_count = len(stories)

    if not stories:
        return (
            f"Fetched {fetched_count} messages, "
            f"{filtered_count} passed the noise filter, "
            f"but no structured knowledge could be extracted."
        )

    # ── 6. Inject into mempalace ─────────────────────────────────────
    from chat_bot.injector import inject_stories

    result = inject_stories(stories)
    stored = result.get("stored", 0)
    errors = result.get("errors", [])

    summary_parts = [
        f"Ingested <#{channel}> — last {hours_back:.0f} h:",
        f"  Messages fetched  : {fetched_count}",
        f"  After noise filter: {filtered_count}",
        f"  Stories extracted : {story_count}",
        f"  Entries stored    : {stored}",
    ]
    if errors:
        summary_parts.append(f"  Errors            : {len(errors)}")
        # Include a capped list of error messages (no raw content)
        for err in errors[:5]:
            summary_parts.append(f"    - {str(err)[:120]}")

    return "\n".join(summary_parts)


# ── Internal helpers ─────────────────────────────────────────────────────────

def _fetch_history(
    channel: str,
    oldest: str,
    limit: int,
) -> list[dict[str, Any]] | str:
    """
    Call conversations.history and return the list of message dicts.
    Returns an error string if the API call fails.
    """
    params = urllib.parse.urlencode({
        "channel": channel,
        "oldest": oldest,
        "limit": limit,
    })
    req = urllib.request.Request(
        f"https://slack.com/api/conversations.history?{params}",
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data: dict[str, Any] = json.loads(resp.read())
    except Exception as exc:
        return f"Slack API request failed: {exc}"

    if not data.get("ok"):
        error = data.get("error", "unknown")
        if error == "channel_not_found":
            return (
                f"Channel '{channel}' not found. "
                "Use the channel ID (e.g. C0123ABCDEF), not its name."
            )
        if error == "not_in_channel":
            return (
                f"The bot is not a member of channel '{channel}'. "
                "Invite the bot first: /invite @YourBot"
            )
        return f"Slack API error: {error}"

    return data.get("messages", [])
