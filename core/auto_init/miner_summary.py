"""
File-level summaries — one entry per file that captures path, imports,
top-level docstring, and the list of defined symbols.

Rationale: the chunker splits files into many focused chunks. For
broad queries ("what does the auth module do?") a chunk shows one
function with no overview. The summary entry gives the AI a clean
file-level overview that complements the chunks.

Symbol extraction uses tree-sitter when available, with a regex fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.auto_init.miner_chunker import _LANG_FOR_EXT, _try_get_parser


_SUMMARY_MAX_CONTENT = 2500   # chars — summaries should be short
_FIRST_LINES_FALLBACK = 30    # preview first N lines when structure not found


@dataclass
class FileSummary:
    text: str
    symbol_count: int


# ── Entry point ──────────────────────────────────────────────────────────────

def build_summary(
    rel_path: str,
    content: str,
    ext: str,
    language: str,
    kind: str,
    top_level_dir: str,
    size: int,
    num_chunks: int,
) -> FileSummary:
    """
    Produce a short, self-contained summary of a file for the palace.
    """
    imports = _extract_imports(content, language)
    doc = _extract_leading_doc(content, language)
    symbols = _extract_symbols(content, ext)

    lines: list[str] = [
        f"File: {rel_path}",
        f"Language: {language} | Kind: {kind} | Dir: {top_level_dir or '(root)'}",
        f"Size: {size} bytes | Chunks: {num_chunks}",
    ]

    if doc:
        lines.append("")
        lines.append("Doc:")
        lines.append(_truncate_multiline(doc, 400))

    if imports:
        lines.append("")
        lines.append("Imports:")
        for imp in imports[:8]:
            lines.append(f"  {imp}")
        if len(imports) > 8:
            lines.append(f"  … {len(imports) - 8} more")

    if symbols:
        lines.append("")
        lines.append("Symbols:")
        for kind_label, name in symbols[:25]:
            lines.append(f"  {kind_label}: {name}")
        if len(symbols) > 25:
            lines.append(f"  … {len(symbols) - 25} more")
    elif not doc and not imports:
        # Last resort — show the first few lines so the AI has something
        preview = "\n".join(content.splitlines()[:_FIRST_LINES_FALLBACK])
        lines.append("")
        lines.append("Preview:")
        lines.append(preview)

    text = "\n".join(lines)
    if len(text) > _SUMMARY_MAX_CONTENT:
        text = text[:_SUMMARY_MAX_CONTENT] + "\n…(summary truncated)"

    return FileSummary(text=text, symbol_count=len(symbols))


# ── Leading doc / module docstring ──────────────────────────────────────────

def _extract_leading_doc(content: str, language: str) -> str:
    """Grab a leading docstring or top-of-file comment block."""
    stripped = content.lstrip()

    if language == "python":
        # Triple-quoted module docstring
        for quote in ('"""', "'''"):
            if stripped.startswith(quote):
                end = stripped.find(quote, 3)
                if end != -1:
                    return stripped[3:end].strip()
        return ""

    if language in {"rust", "go", "javascript", "typescript", "tsx", "java",
                    "kotlin", "c_sharp", "cpp", "c", "swift", "scala", "php"}:
        return _extract_leading_line_comments(stripped)

    if language in {"ruby", "shell", "python"}:
        return _extract_leading_hash_comments(stripped)

    return ""


def _extract_leading_line_comments(text: str) -> str:
    """Collect leading //-style comments (and /** */ block at file top)."""
    # Block comment at top
    if text.startswith("/**") or text.startswith("/*"):
        end = text.find("*/")
        if end != -1:
            raw = text[:end]
            cleaned = re.sub(r"^\s*(/\*+|\*+/?|\*)", "", raw, flags=re.MULTILINE)
            return cleaned.strip()
    # Line comments
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("//"):
            out.append(s.lstrip("/").strip())
        elif s.startswith("///"):
            out.append(s.lstrip("/").strip())
        elif not s:
            # Allow one blank line before we stop
            if out:
                break
        else:
            break
        if len(out) >= 8:
            break
    return "\n".join(out)


def _extract_leading_hash_comments(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#!"):
            continue  # shebang
        if s.startswith("#"):
            out.append(s.lstrip("#").strip())
        elif not s and out:
            break
        else:
            break
        if len(out) >= 8:
            break
    return "\n".join(out)


# ── Imports / includes ──────────────────────────────────────────────────────

_IMPORT_PATTERNS: dict[str, list[str]] = {
    "python":     [r"^\s*(?:from\s+\S+\s+)?import\s+.+$"],
    "javascript": [r"^\s*import\s+.+$", r"^\s*const\s+\w+\s*=\s*require\(.+\)"],
    "typescript": [r"^\s*import\s+.+$"],
    "tsx":        [r"^\s*import\s+.+$"],
    "rust":       [r"^\s*use\s+.+$", r"^\s*extern\s+crate\s+.+$"],
    "go":         [r"^\s*import\s+.+$"],
    "java":       [r"^\s*import\s+.+$"],
    "kotlin":     [r"^\s*import\s+.+$"],
    "c_sharp":    [r"^\s*using\s+.+$"],
    "cpp":        [r"^\s*#include\s+[<\"].+[>\"]$"],
    "c":          [r"^\s*#include\s+[<\"].+[>\"]$"],
    "ruby":       [r"^\s*require(?:_relative)?\s+.+$"],
    "php":        [r"^\s*(?:use|require(?:_once)?|include(?:_once)?)\s+.+$"],
    "swift":      [r"^\s*import\s+.+$"],
    "scala":      [r"^\s*import\s+.+$"],
}


def _extract_imports(content: str, language: str) -> list[str]:
    patterns = _IMPORT_PATTERNS.get(language)
    if not patterns:
        return []

    compiled = [re.compile(p, re.MULTILINE) for p in patterns]
    out: list[str] = []
    seen: set[str] = set()

    # Only look at the first 200 lines — imports are always near the top
    head = "\n".join(content.splitlines()[:200])

    for pat in compiled:
        for m in pat.finditer(head):
            line = m.group(0).strip()
            if line and line not in seen:
                seen.add(line)
                out.append(line)

    return out


# ── Symbol extraction ───────────────────────────────────────────────────────

def _extract_symbols(content: str, ext: str) -> list[tuple[str, str]]:
    """
    Return list of (kind, name) tuples for top-level symbols.
    Uses tree-sitter when available; falls back to regex per language.
    """
    language = _LANG_FOR_EXT.get(ext)
    if language:
        ts_symbols = _extract_symbols_treesitter(content, language)
        if ts_symbols:
            return ts_symbols
    return _extract_symbols_regex(content, ext)


def _extract_symbols_treesitter(content: str, language: str) -> list[tuple[str, str]]:
    """Use tree-sitter to pull top-level symbol kinds + names."""
    parser = _try_get_parser(language)
    if not parser:
        return []

    try:
        source = content.encode("utf-8", errors="ignore")
        tree = parser.parse(source)
    except Exception:
        return []

    from core.auto_init.miner_chunker import _SYMBOL_NODE_TYPES, _extract_symbol_name, _friendly_kind

    wanted = _SYMBOL_NODE_TYPES.get(language, set())
    if not wanted:
        return []

    out: list[tuple[str, str]] = []

    def _walk(node, depth: int = 0) -> None:
        if depth > 4:
            return
        if node.type in wanted:
            name = _extract_symbol_name(node, source)
            kind = _friendly_kind(node.type)
            if name:
                out.append((kind, name))
            return
        for child in node.children:
            _walk(child, depth + 1)

    try:
        _walk(tree.root_node)
    except Exception:
        return []

    return out


# Rough regex fallbacks — keep deliberately simple and only handle the
# most common patterns per language.
_REGEX_SYMBOL_RULES: dict[str, list[tuple[str, str]]] = {
    ".py":  [("function", r"^\s*def\s+(\w+)"), ("class", r"^\s*class\s+(\w+)")],
    ".js":  [("function", r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"),
             ("class", r"^\s*(?:export\s+)?class\s+(\w+)")],
    ".ts":  [("function", r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"),
             ("class", r"^\s*(?:export\s+)?class\s+(\w+)"),
             ("interface", r"^\s*(?:export\s+)?interface\s+(\w+)"),
             ("type", r"^\s*(?:export\s+)?type\s+(\w+)")],
    ".tsx": [("function", r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"),
             ("class", r"^\s*(?:export\s+)?class\s+(\w+)")],
    ".go":  [("function", r"^\s*func\s+(?:\(.+?\)\s+)?(\w+)"),
             ("type", r"^\s*type\s+(\w+)\s+(?:struct|interface)")],
    ".rs":  [("function", r"^\s*(?:pub\s+)?fn\s+(\w+)"),
             ("struct", r"^\s*(?:pub\s+)?struct\s+(\w+)"),
             ("enum", r"^\s*(?:pub\s+)?enum\s+(\w+)"),
             ("trait", r"^\s*(?:pub\s+)?trait\s+(\w+)"),
             ("impl", r"^\s*impl(?:\s+<.+?>)?\s+(\w+)")],
    ".java": [("class", r"^\s*(?:public\s+|private\s+|abstract\s+|final\s+)*class\s+(\w+)"),
              ("method", r"^\s*(?:public\s+|private\s+|protected\s+|static\s+)+\w+\s+(\w+)\s*\(")],
    ".rb":  [("class", r"^\s*class\s+(\w+)"), ("method", r"^\s*def\s+(\w+)")],
    ".php": [("function", r"^\s*function\s+(\w+)"), ("class", r"^\s*class\s+(\w+)")],
    ".cpp": [("function", r"^\s*(?:[a-zA-Z_][\w:]*\s+)+(\w+)\s*\("),
             ("class", r"^\s*class\s+(\w+)"),
             ("struct", r"^\s*struct\s+(\w+)")],
    ".c":   [("function", r"^\s*(?:[a-zA-Z_][\w*]*\s+)+(\w+)\s*\("),
             ("struct", r"^\s*struct\s+(\w+)")],
    ".h":   [("struct", r"^\s*struct\s+(\w+)"),
             ("typedef", r"^\s*typedef\s+.+?\s+(\w+)\s*;")],
    ".cs":  [("class", r"^\s*(?:public\s+|private\s+|internal\s+)?class\s+(\w+)"),
             ("method", r"^\s*(?:public\s+|private\s+|protected\s+|static\s+)+\w+\s+(\w+)\s*\(")],
}


def _extract_symbols_regex(content: str, ext: str) -> list[tuple[str, str]]:
    rules = _REGEX_SYMBOL_RULES.get(ext)
    if not rules:
        return []

    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for kind, pattern in rules:
        regex = re.compile(pattern, re.MULTILINE)
        for m in regex.finditer(content):
            pair = (kind, m.group(1))
            if pair not in seen:
                seen.add(pair)
                out.append(pair)

    return out


# ── helpers ──────────────────────────────────────────────────────────────────

def _truncate_multiline(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"
