"""
Story extractor — converts filtered chat messages into structured
Problem / Solution entries using a question→answer heuristic.
"""

from dataclasses import dataclass, field

from chat_bot.preprocessing.noise_filter import BufferedMessage


@dataclass
class Story:
    """A structured knowledge entry extracted from chat."""
    problem: str
    solution: str
    tags: list[str] = field(default_factory=list)
    source_channel: str = ""
    source_thread_ts: str = ""
    message_count: int = 0


def extract_stories(messages: list[BufferedMessage]) -> list[Story]:
    """
    Take a list of filtered messages and produce structured Stories
    using a question→answer heuristic.
    """
    if not messages:
        return []

    return _heuristic_extract(messages)


# ── Heuristic extraction ────────────────────────────────────────

# The question mark is the only marker used: it signals a direct question in
# virtually all languages and scripts used in technical chat, without any
# English keyword dependency.
_QUESTION_MARK = "?"


def _heuristic_extract(messages: list[BufferedMessage]) -> list[Story]:
    """
    Simple fallback: pair messages that look like questions with the
    next non-question message as a potential answer.
    """
    stories: list[Story] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if _looks_like_question(msg.text):
            # Gather reply(ies) as the solution
            replies: list[str] = []
            j = i + 1
            while j < len(messages) and not _looks_like_question(messages[j].text):
                replies.append(messages[j].text)
                j += 1

            if replies:
                stories.append(Story(
                    problem=msg.text.strip(),
                    solution="\n".join(replies).strip(),
                    tags=[],
                    source_channel=msg.channel,
                    source_thread_ts=msg.thread_ts or msg.ts,
                    message_count=1 + len(replies),
                ))
            i = j
        else:
            i += 1

    return stories


def _looks_like_question(text: str) -> bool:
    return _QUESTION_MARK in text
