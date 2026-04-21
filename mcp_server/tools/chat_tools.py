"""
MCP Tools: Chat — Slack search and question posting.
"""

import json
import os
import urllib.parse
import urllib.request

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN", "")
SLACK_DEFAULT_CHANNEL = os.getenv("SLACK_DEFAULT_CHANNEL", "")


async def check_recent_chat(topic: str, count: int = 10) -> str:
    """Search recent Slack messages for a topic.
    Use to check if the team recently discussed something before searching
    the knowledge base. Returns live Slack context.

    Args:
        topic: Keyword or phrase to search for in Slack.
        count: Maximum messages to return (default 10, max 20).
    """
    token = SLACK_USER_TOKEN or SLACK_BOT_TOKEN
    if not token:
        return (
            "Slack is not configured. Set SLACK_USER_TOKEN (recommended) "
            "or SLACK_BOT_TOKEN in the .env file."
        )

    count = min(count, 20)

    params = urllib.parse.urlencode({"query": topic, "count": count})
    req = urllib.request.Request(
        f"https://slack.com/api/search.messages?{params}",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        return f"Slack search failed: {exc}"

    if not data.get("ok"):
        return f"Slack search error: {data.get('error', 'unknown')}"

    matches = data.get("messages", {}).get("matches", [])
    if not matches:
        return f"No recent Slack messages found for '{topic}'."

    lines = [f"Found {len(matches)} Slack messages for '{_sanitize(topic)}':\n"]
    for m in matches:
        user = m.get("username", "unknown")
        text = _sanitize(m.get("text", "")[:300])
        channel_name = m.get("channel", {}).get("name", "?")
        lines.append(f"  [{channel_name}] @{user}: {text}")

    return "\n".join(lines)


async def ask_team(question: str, channel: str = "") -> str:
    """Post a question to a Slack channel on behalf of the AI assistant.
    Use when you need real-time human input not in the knowledge base.

    Args:
        question: The question to post to the team.
        channel: Slack channel ID. Defaults to SLACK_DEFAULT_CHANNEL.
    """
    if not SLACK_BOT_TOKEN:
        return (
            "Slack is not configured. Set SLACK_BOT_TOKEN in the .env file."
        )

    target = channel or SLACK_DEFAULT_CHANNEL
    if not target:
        return (
            "No channel specified and SLACK_DEFAULT_CHANNEL is not set."
        )

    message = {
        "channel": target,
        "text": f"🤖 *Copilot Question*\n\n{_sanitize(question)}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🤖 *Copilot Question*\n\n{_sanitize(question)}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "Posted by Pneuma on behalf of an AI coding assistant. "
                            "Reply in-thread — the answer may be saved to the knowledge base."
                        ),
                    }
                ],
            },
        ],
    }

    try:
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=json.dumps(message).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                return "Question posted to Slack. A team member will respond shortly."
            return f"Failed to post: {result.get('error', 'unknown error')}"
    except Exception as exc:
        return f"Failed to post question: {exc}"


def _sanitize(text: str) -> str:
    """Prevent Slack mrkdwn injection."""
    return (
        text.replace("```", "` ` `")
        .replace("<!channel>", "")
        .replace("<!here>", "")
        .replace("<!everyone>", "")
    )
