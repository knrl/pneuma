"""
Anonymizer — strips PII (names, emails, IPs) from buffered messages
before they are stored in the knowledge base.

Adapted from the v1.0 summarizer/anonymizer.py for the new
BufferedMessage type.
"""

import re

from chat_bot.preprocessing.noise_filter import BufferedMessage


# Patterns to redact
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_PHONE_RE = re.compile(r"\b\+?\d[\d\-() ]{7,}\d\b")
_SLACK_USER_RE = re.compile(r"<@([A-Z0-9]+)>")

_REDACTED = "[REDACTED]"


def anonymize_messages(
    messages: list[BufferedMessage],
    user_map: dict[str, str] | None = None,
) -> list[BufferedMessage]:
    """
    Return copies of *messages* with PII removed.

    - Slack user mentions ``<@U123>`` → generic labels (``User-1``, ``User-2``…)
    - Email addresses, IP addresses, phone numbers → ``[REDACTED]``

    If *user_map* is provided, it is used and updated in-place so the
    same user ID always gets the same label across batches.
    """
    if user_map is None:
        user_map = {}

    counter = len(user_map)
    result: list[BufferedMessage] = []

    for msg in messages:
        text = msg.text

        # Replace Slack user mentions with stable pseudonyms
        def _replace_mention(match: re.Match) -> str:
            nonlocal counter
            uid = match.group(1)
            if uid not in user_map:
                counter += 1
                user_map[uid] = f"User-{counter}"
            return user_map[uid]

        text = _SLACK_USER_RE.sub(_replace_mention, text)

        # Redact other PII
        text = _EMAIL_RE.sub(_REDACTED, text)
        text = _IP_RE.sub(_REDACTED, text)
        text = _PHONE_RE.sub(_REDACTED, text)

        # Anonymize the user field too
        anon_user = user_map.get(msg.user)
        if not anon_user:
            counter += 1
            user_map[msg.user] = f"User-{counter}"
            anon_user = user_map[msg.user]

        result.append(BufferedMessage(
            user=anon_user,
            text=text,
            channel=msg.channel,
            ts=msg.ts,
            thread_ts=msg.thread_ts,
        ))

    return result
