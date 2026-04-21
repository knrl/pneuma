"""Tests for core/auto_init/miner_chunker — CharChunker + TreeSitterChunker."""

import pytest

from core.auto_init.miner_chunker import (
    CharChunker,
    TreeSitterChunker,
    Chunk,
    get_chunker,
)


# ── CharChunker ─────────────────────────────────────────────────────────────

class TestCharChunker:
    def test_short_content_single_chunk(self):
        c = CharChunker(chunk_size=1500)
        chunks = c.chunk("a.py", "print('hi')")
        assert len(chunks) == 1
        assert chunks[0].kind == "char"
        assert chunks[0].symbol == ""
        assert "print('hi')" in chunks[0].text

    def test_long_content_multiple_chunks(self):
        c = CharChunker(chunk_size=100, chunk_overlap=10)
        chunks = c.chunk("big.py", "x" * 350)
        assert len(chunks) >= 3
        for ch in chunks:
            assert ch.kind == "char"

    def test_overlap_means_next_chunk_starts_earlier(self):
        c = CharChunker(chunk_size=100, chunk_overlap=20)
        content = "a" * 100 + "b" * 100
        chunks = c.chunk("f.py", content)
        # Second chunk should start at offset 100-20 = 80
        # First chunk has "a"*100 → final char is 'a'
        # Second chunk starts with "a"*20 + "b"*80
        assert len(chunks) >= 2
        assert "b" in chunks[1].text

    def test_part_numbering(self):
        c = CharChunker(chunk_size=50, chunk_overlap=5)
        chunks = c.chunk("f.py", "y" * 200)
        assert any("part 1" in ch.text for ch in chunks)
        assert any("part 2" in ch.text for ch in chunks)

    def test_header_included(self):
        c = CharChunker()
        chunks = c.chunk("src/app.py", "x = 1")
        assert "File: src/app.py" in chunks[0].text


# ── get_chunker factory ──────────────────────────────────────────────────────

class TestGetChunker:
    def test_unknown_extension_returns_char_chunker(self):
        ch = get_chunker(".xyz")
        assert isinstance(ch, CharChunker)

    def test_known_extension_returns_some_chunker(self):
        # Either TreeSitter (if available) or Char fallback
        ch = get_chunker(".py")
        assert ch is not None
        chunks = ch.chunk("a.py", "def foo(): pass")
        assert len(chunks) >= 1

    def test_char_chunker_params_propagated(self):
        ch = get_chunker(".xyz", chunk_size=500, chunk_overlap=50)
        assert isinstance(ch, CharChunker)
        assert ch.chunk_size == 500
        assert ch.chunk_overlap == 50


# ── TreeSitterChunker (gated on tree-sitter availability) ───────────────────

def _tree_sitter_available(language: str = "python") -> bool:
    try:
        from tree_sitter_language_pack import get_parser  # type: ignore
        get_parser(language)
        return True
    except Exception:
        pass
    try:
        from tree_sitter_languages import get_parser  # type: ignore
        get_parser(language)
        return True
    except Exception:
        return False


class TestTreeSitterChunker:
    def test_unavailable_falls_back_to_char(self):
        # Force unavailability by using an unsupported language label
        ts = TreeSitterChunker(language="klingon")
        assert ts.is_available is False
        chunks = ts.chunk("f.py", "x = 1\n" * 50)
        assert len(chunks) >= 1
        assert all(ch.kind == "char" for ch in chunks)

    @pytest.mark.skipif(
        not _tree_sitter_available("python"),
        reason="tree-sitter not installed",
    )
    def test_python_function_becomes_one_chunk(self):
        source = (
            "def alpha():\n"
            "    return 1\n"
            "\n"
            "def beta():\n"
            "    return 2\n"
        )
        ts = TreeSitterChunker(language="python")
        chunks = ts.chunk("mod.py", source)

        # Should produce 2 symbol chunks (alpha, beta) — more tolerant of
        # top-level decorations, so allow >= 2
        symbol_chunks = [c for c in chunks if c.kind == "function"]
        assert len(symbol_chunks) >= 2
        symbol_names = {c.symbol for c in symbol_chunks}
        assert "alpha" in symbol_names
        assert "beta" in symbol_names

    @pytest.mark.skipif(
        not _tree_sitter_available("python"),
        reason="tree-sitter not installed",
    )
    def test_python_class_becomes_chunk(self):
        source = (
            "class MyClass:\n"
            "    def method1(self):\n"
            "        return 1\n"
        )
        ts = TreeSitterChunker(language="python")
        chunks = ts.chunk("cls.py", source)
        kinds = [c.kind for c in chunks]
        assert "class" in kinds

    @pytest.mark.skipif(
        not _tree_sitter_available("python"),
        reason="tree-sitter not installed",
    )
    def test_oversized_symbol_splits_to_char_chunks(self):
        # Build a gigantic function
        body = "    pass\n" * 2000
        source = f"def huge():\n{body}"

        ts = TreeSitterChunker(language="python", max_chunk_size=1000)
        chunks = ts.chunk("big.py", source)
        # Oversized symbol should fall back to multiple char-chunks
        assert len(chunks) > 1
        # All should have symbol="huge"
        for c in chunks:
            assert c.symbol == "huge"

    @pytest.mark.skipif(
        not _tree_sitter_available("python"),
        reason="tree-sitter not installed",
    )
    def test_syntax_error_falls_back_cleanly(self):
        broken = "def x(:\n  broken"
        ts = TreeSitterChunker(language="python")
        chunks = ts.chunk("bad.py", broken)
        # Should not raise; should return at least one chunk
        assert len(chunks) >= 1


# ── Integration with miner.get_chunker ──────────────────────────────────────

class TestChunkerFactory:
    def test_chunk_includes_file_header(self):
        ch = get_chunker(".py")
        chunks = ch.chunk("src/main.py", "x = 1")
        assert "File: src/main.py" in chunks[0].text

    @pytest.mark.skipif(
        not _tree_sitter_available("rust"),
        reason="tree-sitter rust not installed",
    )
    def test_rust_functions_extracted(self):
        source = (
            "pub fn alpha() -> i32 { 1 }\n"
            "pub fn beta() -> i32 { 2 }\n"
        )
        ch = get_chunker(".rs")
        chunks = ch.chunk("lib.rs", source)
        # At minimum: two function chunks
        func_chunks = [c for c in chunks if c.kind == "function"]
        assert len(func_chunks) >= 2
