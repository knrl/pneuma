"""
MCP Tools: Import — on-demand document and content ingestion.

Single unified tool for importing files or pasted text into mempalace.
"""

from core.ingestion.doc_parser import import_file, import_content as _import_content


async def import_content(
    file_path: str = "",
    content: str = "",
    doc_type: str = "auto",
    title: str = "",
    wing: str = "",
    room: str = "",
) -> str:
    """Import a file or pasted text into the knowledge base.
    Provide either file_path (for a local file) or content (for pasted text).
    Auto-detects format: Markdown, plain text, Slack JSON, chat logs.
    Chat content is PII-anonymized automatically.

    Args:
        file_path: Absolute path to a local file to import. Leave empty
                   if providing content directly.
        content: Raw text to import (markdown, plain text, JSON, chat log).
                 Leave empty if providing file_path.
        doc_type: Type override — "auto" (default), "decision",
                  "chat-history", or "general".
        title: Optional label for pasted content.
        wing: Target wing. Leave empty for auto-routing.
        room: Target room. Leave empty for auto-routing.
    """
    if file_path:
        try:
            result = import_file(
                path=file_path,
                doc_type=doc_type,
                wing=wing,
                room=room,
            )
        except FileNotFoundError:
            return f"File not found: {file_path}"
        except Exception as exc:
            return f"Import failed: {exc}"
        return _format_summary(result, source=file_path, bump=True)

    if not content or not content.strip():
        return "Nothing to import — provide either file_path or content."

    try:
        result = _import_content(
            content=content,
            doc_type=doc_type,
            title=title,
            wing=wing,
            room=room,
        )
    except Exception as exc:
        return f"Import failed: {exc}"

    return _format_summary(result, source=title or "pasted text", bump=True)


def _format_summary(result: dict, source: str, bump: bool = False) -> str:
    """Build a human-readable summary from the import result dict."""
    entries = result.get('entries_stored', 0)

    if bump and entries > 0:
        from core.background import bump_and_maybe_optimize
        bump_and_maybe_optimize(n=entries)

    lines = [f"Import complete — {source}"]
    lines.append(f"  Document type    : {result.get('doc_type', 'unknown')}")
    lines.append(f"  Entries stored   : {entries}")

    skipped = result.get("duplicates_skipped", 0)
    if skipped:
        lines.append(f"  Duplicates skipped: {skipped}")

    # Chat-specific stats
    if result.get("messages_parsed") is not None:
        lines.append(f"  Messages parsed  : {result['messages_parsed']}")
    if result.get("messages_after_filter") is not None:
        lines.append(f"  After noise filter: {result['messages_after_filter']}")
    if result.get("stories_extracted") is not None:
        lines.append(f"  Stories extracted : {result['stories_extracted']}")

    errors = result.get("errors", [])
    if errors:
        lines.append(f"  Errors           : {len(errors)}")
        for err in errors[:5]:
            lines.append(f"    - {str(err)[:120]}")

    return "\n".join(lines)
