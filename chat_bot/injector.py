"""
Injector — stores extracted stories into the knowledge base
via the core ingestion pipeline (auto-routed).
"""

from chat_bot.preprocessing.story_extractor import Story
from core.ingestion.pipeline import inject_entry


def inject_stories(stories: list[Story]) -> dict:
    """
    Inject a batch of extracted Stories into the palace.

    Each story is turned into embeddable content and passed to
    ``inject_entry()`` which handles routing and storage.

    Returns:
        Summary dict with ``stored`` count and ``errors`` list.
    """
    stored = 0
    errors: list[str] = []

    for story in stories:
        content = (
            f"Problem: {story.problem}\n\n"
            f"Solution: {story.solution}"
        )
        if story.tags:
            content += f"\n\nTags: {', '.join(story.tags)}"

        metadata = {
            "source": "slack",
            "source_channel": story.source_channel,
            "source_thread_ts": story.source_thread_ts,
            "message_count": story.message_count,
            "tags": ",".join(story.tags),
        }

        try:
            inject_entry(content=content, metadata=metadata)
            stored += 1
        except Exception as exc:
            errors.append(str(exc))

    return {"stored": stored, "errors": errors}
