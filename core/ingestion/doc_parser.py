"""
Document parser — on-demand import of decision docs, chat histories,
and general knowledge from local files or raw text.

Supports:
  - Markdown (.md) — split by ## headings
  - Plain text (.txt) — split by double newlines
  - Slack JSON export (.json) — native Slack workspace export format
  - Chat log — ``[timestamp] user: message`` format

Chat-type imports always run through the existing PII anonymizer
and story extractor before storage.
"""

import json
import os
import re
from enum import Enum

from chat_bot.preprocessing.anonymizer import anonymize_messages
from chat_bot.preprocessing.noise_filter import BufferedMessage, filter_messages
from chat_bot.preprocessing.story_extractor import extract_stories
from chat_bot.injector import inject_stories
from core.ingestion.pipeline import inject_entry
from core.palace import check_duplicate


class DocType(str, Enum):
    DECISION = "decision"
    CHAT_HISTORY = "chat-history"
    GENERAL = "general"


# ── Detection ────────────────────────────────────────────────────

# Retain only unambiguous jargon that appears verbatim in technical docs
# regardless of the surrounding prose language.
_DECISION_KEYWORDS = re.compile(
    r"\bADR\b|architecture decision|decision record",
    re.IGNORECASE,
)
_DECISION_HEADINGS = re.compile(
    r"^##?\s*(Decision|Status|Context|Consequences)",
    re.MULTILINE | re.IGNORECASE,
)
_CHAT_LINE_RE = re.compile(
    r"^\[?\d{4}[/-]\d{2}[/-]\d{2}[\sT]\d{2}:\d{2}",
    re.MULTILINE,
)


def detect_doc_type(text: str, file_ext: str = "") -> DocType:
    """
    Auto-detect the document type from content and file extension.

    Priority:
    1. Slack JSON structure → chat-history
    2. Decision keywords / headings → decision
    3. Chat-log line patterns → chat-history
    4. Default → general
    """
    ext = file_ext.lower().lstrip(".")

    # JSON files: try to detect Slack export structure
    if ext == "json":
        try:
            data = json.loads(text)
            if isinstance(data, list) and data and "text" in data[0]:
                return DocType.CHAT_HISTORY
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass

    # Decision doc markers
    if _DECISION_KEYWORDS.search(text) or _DECISION_HEADINGS.search(text):
        return DocType.DECISION

    # Chat log patterns (multiple timestamped lines)
    if len(_CHAT_LINE_RE.findall(text)) >= 3:
        return DocType.CHAT_HISTORY

    return DocType.GENERAL


# ── Parsers ──────────────────────────────────────────────────────

def parse_markdown_sections(text: str) -> list[dict]:
    """
    Split markdown by ``##`` headings into sections.

    Returns a list of ``{title, content, metadata}`` dicts.
    If no headings are found, the entire text is one section.
    """
    heading_re = re.compile(r"^##\s+(.+)", re.MULTILINE)
    matches = list(heading_re.finditer(text))

    if not matches:
        stripped = text.strip()
        if not stripped:
            return []
        return [{"title": "", "content": stripped, "metadata": {}}]

    sections: list[dict] = []

    # Content before the first heading (preamble)
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append({
            "title": "preamble",
            "content": preamble,
            "metadata": {},
        })

    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append({
                "title": title,
                "content": body,
                "metadata": {"section_title": title},
            })

    return sections


_MIN_PARAGRAPH_LENGTH = 50


def parse_plain_text(text: str) -> list[dict]:
    """
    Split plain text by double newlines into paragraph chunks.

    Short paragraphs (< 50 chars) are merged with the next paragraph.
    """
    raw_paragraphs = re.split(r"\n\s*\n", text.strip())
    if not raw_paragraphs:
        return []

    merged: list[str] = []
    buf = ""
    for para in raw_paragraphs:
        para = para.strip()
        if not para:
            continue
        if buf:
            buf += "\n\n" + para
        else:
            buf = para

        if len(buf) >= _MIN_PARAGRAPH_LENGTH:
            merged.append(buf)
            buf = ""

    if buf:
        if merged:
            merged[-1] += "\n\n" + buf
        else:
            merged.append(buf)

    return [{"content": p, "metadata": {}} for p in merged]


def parse_slack_export(text: str) -> list[BufferedMessage]:
    """
    Parse a Slack workspace export JSON file (a list of message objects)
    into BufferedMessage objects for the preprocessing pipeline.
    """
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of Slack messages.")

    messages: list[BufferedMessage] = []
    for msg in data:
        if not isinstance(msg, dict):
            continue
        # Skip bot messages, edits, deletions
        if msg.get("subtype") in ("bot_message", "message_changed", "message_deleted"):
            continue
        msg_text = msg.get("text", "").strip()
        if not msg_text:
            continue
        messages.append(BufferedMessage(
            user=msg.get("user", "unknown"),
            text=msg_text,
            channel=msg.get("channel", "import"),
            ts=msg.get("ts", ""),
            thread_ts=msg.get("thread_ts"),
        ))

    return messages


_CHAT_LOG_LINE_RE = re.compile(
    r"^\[?(\d{4}[/-]\d{2}[/-]\d{2}[\sT]?\d{2}:\d{2}(?::\d{2})?)\]?\s+"
    r"(\S+?):\s+(.+)",
    re.MULTILINE,
)

_SIMPLE_CHAT_RE = re.compile(
    r"^(\S+?):\s+(.+)",
    re.MULTILINE,
)


def parse_chat_log(text: str) -> list[BufferedMessage]:
    """
    Parse a plain-text chat log in the format::

        [2026-04-19 14:30] alice: Hello, how do we deploy?
        [2026-04-19 14:31] bob: Run the deploy script.

    Also supports the simpler ``user: message`` format (no timestamp).
    """
    # Try timestamped format first
    matches = _CHAT_LOG_LINE_RE.findall(text)
    if matches:
        return [
            BufferedMessage(
                user=user,
                text=msg,
                channel="import",
                ts=ts.replace("/", "-"),
                thread_ts=None,
            )
            for ts, user, msg in matches
        ]

    # Fall back to simple user: message format
    matches = _SIMPLE_CHAT_RE.findall(text)
    return [
        BufferedMessage(
            user=user,
            text=msg,
            channel="import",
            ts="",
            thread_ts=None,
        )
        for user, msg in matches
    ]


# ── Import orchestrators ─────────────────────────────────────────

_DUP_THRESHOLD = 0.9


def import_file(
    path: str,
    doc_type: str = "auto",
    wing: str = "",
    room: str = "",
) -> dict:
    """
    Read a local file and import its contents into mempalace.

    Args:
        path: Absolute or relative path to the file.
        doc_type: ``"auto"``, ``"decision"``, ``"chat-history"``, or ``"general"``.
        wing: Target wing override (empty = auto-route).
        room: Target room override (empty = auto-route).

    Returns:
        Summary dict: ``{entries_stored, duplicates_skipped, doc_type, errors}``.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, encoding="utf-8") as f:
        content = f.read()

    _, ext = os.path.splitext(path)
    filename = os.path.basename(path)

    return _import(
        content=content,
        file_ext=ext,
        doc_type=doc_type,
        wing=wing,
        room=room,
        source_label=filename,
    )


def import_content(
    content: str,
    doc_type: str = "auto",
    title: str = "",
    wing: str = "",
    room: str = "",
) -> dict:
    """
    Import raw text/JSON content into mempalace (no file I/O).

    Args:
        content: Raw text (markdown, plain text, JSON, or chat log).
        doc_type: ``"auto"``, ``"decision"``, ``"chat-history"``, or ``"general"``.
        title: Optional title for the imported content.
        wing: Target wing override (empty = auto-route).
        room: Target room override (empty = auto-route).

    Returns:
        Summary dict: ``{entries_stored, duplicates_skipped, doc_type, errors}``.
    """
    return _import(
        content=content,
        file_ext="",
        doc_type=doc_type,
        wing=wing,
        room=room,
        source_label=title or "paste",
    )


# ── Core import logic ────────────────────────────────────────────

def _import(
    content: str,
    file_ext: str,
    doc_type: str,
    wing: str,
    room: str,
    source_label: str,
) -> dict:
    """Shared import logic for both file and content imports."""
    # Resolve doc type
    if doc_type == "auto":
        detected = detect_doc_type(content, file_ext)
    else:
        detected = DocType(doc_type)

    if detected == DocType.CHAT_HISTORY:
        return _import_chat(content, file_ext, source_label)
    else:
        return _import_sections(content, file_ext, detected, wing, room, source_label)


def _import_chat(
    content: str,
    file_ext: str,
    source_label: str,
) -> dict:
    """Import chat-type content through the full preprocessing pipeline."""
    ext = file_ext.lower().lstrip(".")

    # Parse into BufferedMessage list
    if ext == "json":
        messages = parse_slack_export(content)
    else:
        messages = parse_chat_log(content)

    if not messages:
        return {
            "entries_stored": 0,
            "duplicates_skipped": 0,
            "doc_type": DocType.CHAT_HISTORY.value,
            "errors": ["No messages could be parsed from the input."],
        }

    # Run through existing preprocessing pipeline (always anonymizes)
    filtered = filter_messages(messages)
    if not filtered:
        return {
            "entries_stored": 0,
            "duplicates_skipped": 0,
            "doc_type": DocType.CHAT_HISTORY.value,
            "errors": [],
            "messages_parsed": len(messages),
            "messages_after_filter": 0,
        }

    anonymized = anonymize_messages(filtered)
    stories = extract_stories(anonymized)

    if not stories:
        return {
            "entries_stored": 0,
            "duplicates_skipped": 0,
            "doc_type": DocType.CHAT_HISTORY.value,
            "errors": [],
            "messages_parsed": len(messages),
            "messages_after_filter": len(filtered),
            "stories_extracted": 0,
        }

    result = inject_stories(stories)

    return {
        "entries_stored": result.get("stored", 0),
        "duplicates_skipped": 0,
        "doc_type": DocType.CHAT_HISTORY.value,
        "errors": result.get("errors", []),
        "messages_parsed": len(messages),
        "messages_after_filter": len(filtered),
        "stories_extracted": len(stories),
    }


def _import_sections(
    content: str,
    file_ext: str,
    doc_type: DocType,
    wing: str,
    room: str,
    source_label: str,
) -> dict:
    """Import decision / general doc as sectioned entries."""
    ext = file_ext.lower().lstrip(".")

    if ext in ("md", "markdown") or content.lstrip().startswith("#"):
        sections = parse_markdown_sections(content)
    else:
        sections = parse_plain_text(content)

    if not sections:
        return {
            "entries_stored": 0,
            "duplicates_skipped": 0,
            "doc_type": doc_type.value,
            "errors": ["No content could be parsed from the input."],
        }

    stored = 0
    skipped = 0
    errors: list[str] = []

    for section in sections:
        section_content = section["content"]

        # Duplicate check
        try:
            dup = check_duplicate(section_content, threshold=_DUP_THRESHOLD)
            if dup.get("is_duplicate"):
                skipped += 1
                continue
        except Exception:
            pass  # If dedup check fails, proceed with storage

        metadata: dict = {
            "source": "manual-import",
            "doc_type": doc_type.value,
            "original_file": source_label,
        }
        metadata.update(section.get("metadata", {}))

        if wing and room:
            metadata["wing"] = wing
            metadata["room"] = room

        try:
            inject_entry(content=section_content, metadata=metadata)
            stored += 1
        except Exception as exc:
            errors.append(str(exc))

    return {
        "entries_stored": stored,
        "duplicates_skipped": skipped,
        "doc_type": doc_type.value,
        "errors": errors,
    }
