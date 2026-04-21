"""
Chunking strategies for the miner.

Two implementations:
  - CharChunker      : character-based windows with overlap (always works)
  - TreeSitterChunker: splits on AST symbol boundaries (functions, classes,
                       methods). Requires `tree_sitter` + language grammars.
                       Falls back to CharChunker per-file on any failure.

Each Chunk carries:
  - text    : the chunk body (already includes file path header)
  - symbol  : qualified symbol name when available ("JwtValidator::verify")
  - kind    : "function" | "class" | "module" | "block" | "char"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ── Public types ─────────────────────────────────────────────────────────────


@dataclass
class Chunk:
    text: str
    symbol: str = ""
    kind: str = "char"


# ── Char-based fallback ──────────────────────────────────────────────────────


class CharChunker:
    """Windowed char chunking with overlap. Always available, no deps."""

    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, rel_path: str, content: str) -> list[Chunk]:
        if len(content) <= self.chunk_size:
            return [Chunk(
                text=f"File: {rel_path}\n\n{content}",
                symbol="",
                kind="char",
            )]

        parts: list[Chunk] = []
        offset = 0
        part_num = 1
        while offset < len(content):
            piece = content[offset: offset + self.chunk_size]
            parts.append(Chunk(
                text=f"File: {rel_path} (part {part_num})\n\n{piece}",
                symbol="",
                kind="char",
            ))
            offset += self.chunk_size - self.chunk_overlap
            part_num += 1

        return parts


# ── Tree-sitter chunker ──────────────────────────────────────────────────────

# tree-sitter-languages / tree-sitter-language-pack both work. We try the
# newer pack first, then the older languages package, then give up.

_LANG_FOR_EXT = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "tsx",
    ".java": "java",
    ".kt": "kotlin",
    ".cs": "c_sharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".c": "c", ".h": "c",
    ".lua": "lua",
    ".scala": "scala",
    ".ex": "elixir", ".exs": "elixir",
}

# Node types that we treat as top-level "symbols" worth extracting per language.
# Minimal + pragmatic set — missing entries fall through to whole-file.
_SYMBOL_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition", "class_definition", "decorated_definition"},
    "javascript": {"function_declaration", "class_declaration", "method_definition",
                   "arrow_function", "export_statement"},
    "typescript": {"function_declaration", "class_declaration", "method_definition",
                   "interface_declaration", "type_alias_declaration", "enum_declaration",
                   "export_statement"},
    "tsx": {"function_declaration", "class_declaration", "method_definition",
            "interface_declaration", "type_alias_declaration", "enum_declaration"},
    "java": {"method_declaration", "class_declaration", "interface_declaration",
             "enum_declaration", "constructor_declaration"},
    "kotlin": {"function_declaration", "class_declaration", "object_declaration"},
    "c_sharp": {"method_declaration", "class_declaration", "interface_declaration",
                "struct_declaration", "enum_declaration", "namespace_declaration"},
    "go": {"function_declaration", "method_declaration", "type_declaration"},
    "rust": {"function_item", "struct_item", "enum_item", "impl_item", "trait_item",
             "mod_item", "type_item"},
    "ruby": {"method", "class", "module", "singleton_method"},
    "php": {"function_definition", "class_declaration", "method_declaration",
            "interface_declaration", "trait_declaration"},
    "swift": {"function_declaration", "class_declaration", "protocol_declaration",
              "struct_declaration", "enum_declaration"},
    "cpp": {"function_definition", "class_specifier", "struct_specifier",
            "namespace_definition", "declaration"},
    "c": {"function_definition", "struct_specifier", "enum_specifier"},
    "lua": {"function_declaration", "function_definition"},
    "scala": {"function_definition", "class_definition", "trait_definition",
              "object_definition"},
    "elixir": {"call"},  # defmodule/def/defp are parsed as calls in elixir-ts
}


def _try_get_parser(language: str):
    """Return a tree-sitter Parser for the given language, or None on failure."""
    try:
        # Newer, actively maintained
        from tree_sitter_language_pack import get_parser  # type: ignore
        return get_parser(language)
    except Exception:
        pass
    try:
        # Older, widely available
        from tree_sitter_languages import get_parser  # type: ignore
        return get_parser(language)
    except Exception:
        return None


def _extract_symbol_name(node, source: bytes) -> str:
    """Best-effort: pull an identifier name out of a symbol node."""
    for child in node.children:
        if child.type in {"identifier", "property_identifier", "type_identifier",
                          "field_identifier", "scoped_identifier",
                          "qualified_identifier", "name", "constant"}:
            try:
                return source[child.start_byte:child.end_byte].decode("utf-8", errors="ignore")
            except Exception:
                return ""
    return ""


class TreeSitterChunker:
    """AST-aware chunker. One chunk per top-level symbol."""

    def __init__(
        self,
        language: str,
        max_chunk_size: int = 4000,
        fallback: CharChunker | None = None,
    ):
        self.language = language
        self.max_chunk_size = max_chunk_size
        self.fallback = fallback or CharChunker()
        self._parser = _try_get_parser(language)

    @property
    def is_available(self) -> bool:
        return self._parser is not None

    def chunk(self, rel_path: str, content: str) -> list[Chunk]:
        if not self._parser:
            return self.fallback.chunk(rel_path, content)

        try:
            source = content.encode("utf-8", errors="ignore")
            tree = self._parser.parse(source)
            root = tree.root_node
        except Exception:
            return self.fallback.chunk(rel_path, content)

        wanted_types = _SYMBOL_NODE_TYPES.get(self.language, set())
        if not wanted_types:
            return self.fallback.chunk(rel_path, content)

        symbols: list[tuple[int, int, str, str]] = []  # (start, end, name, kind)

        def _walk(node, depth: int = 0) -> None:
            if depth > 4:  # avoid exploring too deep
                return
            if node.type in wanted_types:
                name = _extract_symbol_name(node, source)
                kind = _friendly_kind(node.type)
                symbols.append((node.start_byte, node.end_byte, name, kind))
                return  # don't recurse inside a symbol
            for child in node.children:
                _walk(child, depth + 1)

        _walk(root)

        if not symbols:
            return self.fallback.chunk(rel_path, content)

        chunks: list[Chunk] = []
        for start, end, name, kind in symbols:
            body = source[start:end].decode("utf-8", errors="ignore")
            if len(body) > self.max_chunk_size:
                # Oversized symbol — fall back to windowed char chunks for it
                sub = self.fallback.chunk(rel_path, body)
                for c in sub:
                    c.symbol = name
                    c.kind = kind
                chunks.extend(sub)
                continue

            header = f"File: {rel_path}\nSymbol: {name}\nKind: {kind}\n\n"
            chunks.append(Chunk(text=header + body, symbol=name, kind=kind))

        if not chunks:
            return self.fallback.chunk(rel_path, content)

        return chunks


def _friendly_kind(node_type: str) -> str:
    if "function" in node_type or "method" in node_type:
        return "function"
    if "class" in node_type or "struct" in node_type or "object" in node_type:
        return "class"
    if "interface" in node_type or "trait" in node_type or "protocol" in node_type:
        return "interface"
    if "module" in node_type or "namespace" in node_type or "mod_item" in node_type:
        return "module"
    if "enum" in node_type:
        return "enum"
    if "impl" in node_type:
        return "impl"
    if "type" in node_type:
        return "type"
    return "block"


# ── Factory ──────────────────────────────────────────────────────────────────


def get_chunker(
    ext: str,
    chunk_size: int = 1500,
    chunk_overlap: int = 150,
) -> CharChunker | TreeSitterChunker:
    """
    Return the best available chunker for a file extension.
    Always returns a usable chunker (falls back to CharChunker).
    """
    char = CharChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    lang = _LANG_FOR_EXT.get(ext)
    if not lang:
        return char

    ts = TreeSitterChunker(
        language=lang,
        max_chunk_size=max(chunk_size * 2, 3000),
        fallback=char,
    )
    if ts.is_available:
        return ts
    return char
