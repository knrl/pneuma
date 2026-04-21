"""
MCP Tool: ingest_teams_channel
Fetch Microsoft Teams channel history via Graph API and store extracted knowledge.

Auth: client credentials flow (app-only).
Required Azure AD app permissions (application, admin-consented):
  - ChannelMessage.Read.All
"""

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any

TEAMS_CLIENT_ID = os.getenv("TEAMS_CLIENT_ID", "")
TEAMS_CLIENT_SECRET = os.getenv("TEAMS_CLIENT_SECRET", "")
TEAMS_TENANT_ID = os.getenv("TEAMS_TENANT_ID", "")
TEAMS_DEFAULT_TEAM_ID = os.getenv("TEAMS_TEAM_ID", "")

_ALLOWED_CHANNELS: set[str] = {
    c.strip()
    for c in os.getenv("TEAMS_ALLOWED_CHANNEL_IDS", "").split(",")
    if c.strip()
}

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_token_cache: dict = {}


def _get_access_token() -> str:
    """Acquire an app-only access token, cached until near-expiry."""
    now = time.time()
    if _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["access_token"]

    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": TEAMS_CLIENT_ID,
        "client_secret": TEAMS_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
    }).encode()

    req = urllib.request.Request(
        f"https://login.microsoftonline.com/{TEAMS_TENANT_ID}/oauth2/v2.0/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
    except Exception as exc:
        raise RuntimeError(f"Teams token request failed: {exc}")

    if "access_token" not in result:
        raise RuntimeError(
            f"Teams auth error: {result.get('error_description', result.get('error', result))}"
        )

    _token_cache["access_token"] = result["access_token"]
    _token_cache["expires_at"] = now + result.get("expires_in", 3600)
    return _token_cache["access_token"]


def _graph_get(path: str) -> dict[str, Any]:
    token = _get_access_token()
    req = urllib.request.Request(
        f"{_GRAPH_BASE}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _fetch_channel_messages(
    team_id: str,
    channel_id: str,
    oldest_iso: str,
    limit: int,
) -> list[dict[str, Any]] | str:
    """Fetch up to *limit* messages from a channel since *oldest_iso* (ISO 8601)."""
    path = (
        f"/teams/{team_id}/channels/{channel_id}/messages"
        f"?$top={min(limit, 50)}&$filter=lastModifiedDateTime ge {oldest_iso}"
    )
    messages: list[dict] = []
    try:
        while len(messages) < limit:
            data = _graph_get(path)
            batch = data.get("value", [])
            messages.extend(batch)
            next_link = data.get("@odata.nextLink", "")
            if not next_link or len(messages) >= limit:
                break
            # Strip base URL from nextLink
            path = next_link.replace(_GRAPH_BASE, "")
    except RuntimeError as exc:
        return str(exc)
    except Exception as exc:
        return f"Graph API error: {exc}"

    return messages[:limit]


async def ingest_teams_channel(
    channel_id: str,
    team_id: str = "",
    hours_back: float = 24.0,
    limit: int = 200,
) -> str:
    """Fetch recent messages from a Microsoft Teams channel and store extracted knowledge.
    Messages are noise-filtered, anonymized, and extracted into problem/solution stories.

    Args:
        channel_id: Teams channel ID (from channel URL or admin center).
        team_id: Teams team ID. Defaults to TEAMS_TEAM_ID from .env.
        hours_back: Hours of history to fetch (default 24). Use 168 for a week.
        limit: Max messages to fetch before filtering (default 200).
    """
    if not all([TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET, TEAMS_TENANT_ID]):
        return (
            "Microsoft Teams is not configured. "
            "Set TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET, and TEAMS_TENANT_ID in .env."
        )

    resolved_team = team_id or TEAMS_DEFAULT_TEAM_ID
    if not resolved_team:
        return "No team_id provided and TEAMS_TEAM_ID is not set in .env."

    if _ALLOWED_CHANNELS and channel_id not in _ALLOWED_CHANNELS:
        return (
            f"Channel '{channel_id}' is not in the allowed list. "
            "Add it to TEAMS_ALLOWED_CHANNEL_IDS in .env."
        )

    from datetime import datetime, timezone, timedelta
    oldest_dt = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    oldest_iso = oldest_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    raw = _fetch_channel_messages(resolved_team, channel_id, oldest_iso, limit)
    if isinstance(raw, str):
        return raw

    fetched_count = len(raw)
    if fetched_count == 0:
        return f"No messages found in channel '{channel_id}' for the last {hours_back:.0f} h."

    # Convert to BufferedMessage (reuse existing pipeline)
    from chat_bot.preprocessing.noise_filter import BufferedMessage

    buffered = []
    for m in raw:
        msg_type = m.get("messageType", "")
        if msg_type != "message":
            continue
        body = m.get("body", {})
        # Strip HTML tags from Teams message body
        text = _strip_html(body.get("content", "")).strip()
        if not text:
            continue
        user = (m.get("from") or {}).get("user", {}).get("id", "unknown")
        buffered.append(BufferedMessage(
            user=user,
            text=text,
            channel=channel_id,
            ts=m.get("createdDateTime", ""),
        ))

    if not buffered:
        return f"Fetched {fetched_count} messages but none were processable."

    from chat_bot.preprocessing.noise_filter import filter_messages
    filtered = filter_messages(buffered)
    filtered_count = len(filtered)

    if not filtered:
        return (
            f"Fetched {fetched_count} messages from channel '{channel_id}' "
            f"but all were filtered as noise. Nothing stored."
        )

    from chat_bot.preprocessing.anonymizer import anonymize_messages
    anonymized = anonymize_messages(filtered)

    from chat_bot.preprocessing.story_extractor import extract_stories
    stories = extract_stories(anonymized)
    story_count = len(stories)

    if not stories:
        return (
            f"Fetched {fetched_count} messages, "
            f"{filtered_count} passed the noise filter, "
            f"but no structured knowledge could be extracted."
        )

    from chat_bot.injector import inject_stories
    result = inject_stories(stories)
    stored = result.get("stored", 0)
    errors = result.get("errors", [])

    summary = [
        f"Ingested Teams channel '{channel_id}' — last {hours_back:.0f} h:",
        f"  Messages fetched  : {fetched_count}",
        f"  After noise filter: {filtered_count}",
        f"  Stories extracted : {story_count}",
        f"  Entries stored    : {stored}",
    ]
    if errors:
        summary.append(f"  Errors            : {len(errors)}")
        for err in errors[:5]:
            summary.append(f"    - {str(err)[:120]}")

    return "\n".join(summary)


def _strip_html(text: str) -> str:
    """Remove HTML tags from Teams message body content."""
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()
