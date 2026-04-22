"""
MCP Tools: Import — on-demand document and content ingestion.

Single unified tool for importing files or pasted text into mempalace.
"""

import os
from pathlib import Path

from core.ingestion.doc_parser import import_file, import_content as _import_content


def _resolve_safe_path(file_path: str) -> tuple[Path, str | None]:
    """Resolve path and verify it sits within an allowed root.

    Allowed roots (checked in order):
      1. PNEUMA_PROJECT env var (the configured project directory)
      2. The user's home directory
      3. Any colon-separated paths in PNEUMA_IMPORT_ROOTS

    Returns (resolved_path, error_message). error_message is None on success.
    """
    try:
        resolved = Path(file_path).resolve()
    except Exception as exc:
        return Path(file_path), f"Invalid file path: {exc}"

    if not resolved.is_file():
        return resolved, f"Not a regular file: {resolved}"

    allowed: list[Path] = [Path.home()]
    project = os.environ.get("PNEUMA_PROJECT", "")
    if project:
        allowed.append(Path(project).resolve())
    for extra in os.environ.get("PNEUMA_IMPORT_ROOTS", "").split(os.pathsep):
        if extra.strip():
            allowed.append(Path(extra.strip()).resolve())

    if not any(resolved.is_relative_to(root) for root in allowed):
        roots_str = ", ".join(str(r) for r in allowed)
        return resolved, (
            f"Access denied: {resolved} is outside allowed directories "
            f"({roots_str}). Set PNEUMA_IMPORT_ROOTS to allow additional paths."
        )

    return resolved, None


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
        resolved, err = _resolve_safe_path(file_path)
        if err:
            return err
        try:
            result = import_file(
                path=str(resolved),
                doc_type=doc_type,
                wing=wing,
                room=room,
            )
        except FileNotFoundError:
            return f"File not found: {resolved}"
        except Exception as exc:
            return f"Import failed: {exc}"
        return _format_summary(result, source=str(resolved), bump=True)

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
