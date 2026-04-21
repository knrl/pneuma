"""
MCP Tools: Microsoft Teams — channel search, question posting, and escalation.

Posting uses an Incoming Webhook URL (created per-channel in Teams).
Reading/search reuses the Graph API token from teams_ingest_tools.

Webhook setup (per channel):
  Teams channel → ... → Connectors → Incoming Webhook → Create → copy URL
"""

import json
import os
import urllib.request

TEAMS_DEFAULT_WEBHOOK_URL = os.getenv("TEAMS_DEFAULT_WEBHOOK_URL", "")
TEAMS_ESCALATION_WEBHOOK_URL = os.getenv("TEAMS_ESCALATION_WEBHOOK_URL", "")
TEAMS_DEFAULT_TEAM_ID = os.getenv("TEAMS_TEAM_ID", "")
TEAMS_ALLOWED_CHANNEL_IDS: list[str] = [
    c.strip()
    for c in os.getenv("TEAMS_ALLOWED_CHANNEL_IDS", "").split(",")
    if c.strip()
]


# ── Internal helpers ─────────────────────────────────────────────────────────

def _sanitize(text: str) -> str:
    """Strip Teams-specific injection patterns before posting."""
    import re
    # Remove HTML tags that could be injected into webhook content
    text = re.sub(r"<[^>]+>", "", text)
    # Remove Teams @mention markup
    text = re.sub(r"<at>[^<]*</at>", "", text)
    return text.strip()


def _post_webhook(webhook_url: str, payload: dict) -> str:
    """POST a MessageCard payload to a Teams incoming webhook URL."""
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            # Teams webhooks return "1" on success
            body = resp.read().decode("utf-8", errors="replace").strip()
            if body == "1":
                return "ok"
            return f"unexpected response: {body}"
    except Exception as exc:
        return f"error: {exc}"


# ── MCP Tools ────────────────────────────────────────────────────────────────

async def check_recent_teams_chat(topic: str, count: int = 10) -> str:
    """Search recent Microsoft Teams channel messages for a topic.
    Fetches from all channels in TEAMS_ALLOWED_CHANNEL_IDS and filters locally.

    Args:
        topic: Keyword or phrase to search for.
        count: Maximum messages to return (default 10, max 20).
    """
    from mcp_server.tools.teams_ingest_tools import (
        _fetch_channel_messages,
        _strip_html,
        TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET, TEAMS_TENANT_ID,
    )

    if not all([TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET, TEAMS_TENANT_ID]):
        return (
            "Microsoft Teams is not configured. "
            "Set TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET, and TEAMS_TENANT_ID in .env."
        )

    if not TEAMS_ALLOWED_CHANNEL_IDS:
        return "No channels configured. Set TEAMS_ALLOWED_CHANNEL_IDS in .env."

    if not TEAMS_DEFAULT_TEAM_ID:
        return "TEAMS_TEAM_ID is not set in .env."

    count = min(count, 20)
    topic_lower = topic.lower()
    matches = []

    from datetime import datetime, timezone, timedelta
    oldest_iso = (datetime.now(timezone.utc) - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%SZ")

    for channel_id in TEAMS_ALLOWED_CHANNEL_IDS:
        raw = _fetch_channel_messages(TEAMS_DEFAULT_TEAM_ID, channel_id, oldest_iso, limit=50)
        if isinstance(raw, str):
            continue
        for m in raw:
            if m.get("messageType") != "message":
                continue
            text = _strip_html(m.get("body", {}).get("content", ""))
            if topic_lower in text.lower():
                user = (m.get("from") or {}).get("user", {}).get("displayName", "unknown")
                matches.append(f"  [channel:{channel_id}] @{user}: {text[:300]}")
                if len(matches) >= count:
                    break
        if len(matches) >= count:
            break

    if not matches:
        return f"No recent Teams messages found for '{_sanitize(topic)}'."

    lines = [f"Found {len(matches)} Teams messages for '{_sanitize(topic)}':\n"]
    lines.extend(matches)
    return "\n".join(lines)


async def ask_teams_channel(question: str, webhook_url: str = "") -> str:
    """Post a question to a Microsoft Teams channel on behalf of the AI assistant.
    Use when you need real-time human input not found in the knowledge base.

    Args:
        question: The question to post.
        webhook_url: Incoming webhook URL for the target channel.
                     Defaults to TEAMS_DEFAULT_WEBHOOK_URL from .env.
    """
    target = webhook_url or TEAMS_DEFAULT_WEBHOOK_URL
    if not target:
        return (
            "No webhook URL provided and TEAMS_DEFAULT_WEBHOOK_URL is not set in .env."
        )

    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": "AI Assistant Question",
        "sections": [
            {
                "activityTitle": "🤖 AI Assistant Question",
                "activityText": _sanitize(question),
            },
            {
                "text": (
                    "_Posted by Pneuma on behalf of an AI coding assistant. "
                    "Reply here — the answer may be saved to the knowledge base._"
                ),
            },
        ],
    }

    result = _post_webhook(target, payload)
    if result == "ok":
        return "Question posted to Teams channel. A team member will respond shortly."
    return f"Failed to post question: {result}"


async def escalate_to_teams(question: str, code_context: str) -> str:
    """Escalate an unanswerable question to a Microsoft Teams channel.
    Use when search_memory returns low-confidence results.

    Args:
        question: The developer's original question.
        code_context: Relevant code snippet or file context.
    """
    target = TEAMS_ESCALATION_WEBHOOK_URL or TEAMS_DEFAULT_WEBHOOK_URL
    if not target:
        return (
            "Escalation is not configured. "
            "Set TEAMS_ESCALATION_WEBHOOK_URL in .env."
        )

    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": "FF0000",
        "summary": "Knowledge Escalation Request",
        "sections": [
            {
                "activityTitle": "🆘 Knowledge Escalation Request",
                "activityText": (
                    "The AI could not find a confident answer. "
                    "Please reply in this thread."
                ),
            },
            {
                "title": "Question",
                "text": _sanitize(question),
            },
            {
                "title": "Code Context",
                "text": f"```\n{_sanitize(code_context[:1500])}\n```",
            },
        ],
    }

    result = _post_webhook(target, payload)
    if result == "ok":
        return (
            "Escalation sent to Teams. "
            "A team member will respond shortly."
        )
    return f"Escalation failed: {result}"
