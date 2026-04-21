"""
MCP Tool: escalate_to_human
Routes unanswerable questions to a designated Slack channel.
"""

import os
import json
import urllib.request

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
ESCALATION_CHANNEL = os.getenv("ESCALATION_CHANNEL", "")


async def escalate_to_human(code_context: str, question: str) -> str:
    """Escalate a question to a human expert via Slack when confidence is low.
    Use when search_memory returns low-confidence results or no results.
    Sends code context and the question to the engineering channel.

    Args:
        code_context: The relevant code snippet or file context.
        question: The developer's original question.
    """
    if not SLACK_BOT_TOKEN or not ESCALATION_CHANNEL:
        return (
            "Escalation is not configured. Set SLACK_BOT_TOKEN and "
            "ESCALATION_CHANNEL in the .env file."
        )

    # Build the Slack message
    message = {
        "channel": ESCALATION_CHANNEL,
        "text": "\U0001f198 *Knowledge Escalation Request*",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "\U0001f198 Knowledge Escalation Request"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Question:*\n{_sanitize(question)}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Code Context:*\n```{_sanitize(code_context[:1500])}```"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "This question was escalated because the AI could not "
                            "find a confident answer. Reply in this thread to help — "
                            "your answer may be saved to the knowledge base."
                        )
                    }
                ]
            }
        ]
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
                return (
                    "Escalation sent successfully. A notification has been posted "
                    f"to the engineering channel. A team member will respond shortly."
                )
            else:
                return f"Escalation failed: {result.get('error', 'unknown error')}"

    except Exception as e:
        return f"Escalation failed due to a network error: {str(e)}"


def _sanitize(text: str) -> str:
    """Basic input sanitization to prevent Slack injection."""
    return (
        text.replace("```", "` ` `")
        .replace("<!channel>", "")
        .replace("<!here>", "")
        .replace("<!everyone>", "")
    )

