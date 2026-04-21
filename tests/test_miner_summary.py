"""Tests for core/auto_init/miner_summary — file-level summary generation."""

import pytest

from core.auto_init.miner_summary import (
    build_summary,
    _extract_imports,
    _extract_leading_doc,
    _extract_symbols_regex,
)


# ── Imports ─────────────────────────────────────────────────────────────────

class TestExtractImports:
    def test_python(self):
        src = (
            "import os\n"
            "from pathlib import Path\n"
            "from typing import List, Dict\n"
            "\n"
            "def main(): pass\n"
        )
        imps = _extract_imports(src, "python")
        assert any("import os" in i for i in imps)
        assert any("from pathlib" in i for i in imps)

    def test_rust(self):
        src = "use std::collections::HashMap;\nuse serde::Serialize;\n"
        imps = _extract_imports(src, "rust")
        assert len(imps) >= 2
        assert any("HashMap" in i for i in imps)

    def test_typescript(self):
        src = "import { Foo } from './foo';\nimport Bar from 'bar';\n"
        imps = _extract_imports(src, "typescript")
        assert len(imps) >= 2

    def test_go(self):
        src = "import \"fmt\"\nimport \"os\"\n"
        imps = _extract_imports(src, "go")
        assert len(imps) >= 2

    def test_c_include(self):
        src = "#include <stdio.h>\n#include \"local.h\"\n"
        imps = _extract_imports(src, "c")
        assert any("stdio.h" in i for i in imps)

    def test_unknown_language(self):
        assert _extract_imports("whatever", "klingon") == []

    def test_dedupe(self):
        # Same import appearing twice should show once
        src = "use foo::bar;\nuse foo::bar;\n"
        imps = _extract_imports(src, "rust")
        assert len(imps) == 1


# ── Leading documentation ───────────────────────────────────────────────────

class TestExtractLeadingDoc:
    def test_python_module_docstring(self):
        src = '"""Module for auth handling."""\n\ndef x(): pass\n'
        assert "auth handling" in _extract_leading_doc(src, "python")

    def test_python_triple_single_quote(self):
        src = "'''Single quote doc.'''\n\ndef x(): pass\n"
        assert "Single quote doc" in _extract_leading_doc(src, "python")

    def test_python_no_doc(self):
        src = "def x(): pass\n"
        assert _extract_leading_doc(src, "python") == ""

    def test_rust_line_comments(self):
        src = (
            "// JWT validator module.\n"
            "// Handles token verification.\n"
            "\n"
            "pub fn verify() {}\n"
        )
        doc = _extract_leading_doc(src, "rust")
        assert "JWT validator" in doc
        assert "token verification" in doc

    def test_cpp_block_comment(self):
        src = (
            "/**\n"
            " * PacketHandler class.\n"
            " * Parses incoming packets.\n"
            " */\n"
            "class PacketHandler { };\n"
        )
        doc = _extract_leading_doc(src, "cpp")
        assert "PacketHandler" in doc

    def test_ruby_hash_comments(self):
        src = "# A Ruby module.\n# Does things.\n\nclass M\nend\n"
        doc = _extract_leading_doc(src, "ruby")
        assert "Ruby module" in doc

    def test_shebang_ignored(self):
        src = "#!/usr/bin/env python\n# Real doc here.\n"
        doc = _extract_leading_doc(src, "python")
        # Python uses """ for module docstrings, so this falls through
        # to _extract_leading_hash_comments via the alias — test that
        # _extract_leading_hash_comments skips shebangs
        from core.auto_init.miner_summary import _extract_leading_hash_comments
        out = _extract_leading_hash_comments(src)
        assert "Real doc" in out
        assert "/usr/bin" not in out


# ── Symbol extraction (regex fallback) ───────────────────────────────────────

class TestExtractSymbolsRegex:
    def test_python_functions_and_classes(self):
        src = (
            "def alpha():\n"
            "    pass\n"
            "\n"
            "class Beta:\n"
            "    pass\n"
            "\n"
            "def gamma(x, y):\n"
            "    return x + y\n"
        )
        symbols = _extract_symbols_regex(src, ".py")
        names = {s[1] for s in symbols}
        kinds = {s[0] for s in symbols}
        assert "alpha" in names
        assert "Beta" in names
        assert "gamma" in names
        assert "function" in kinds
        assert "class" in kinds

    def test_rust_symbols(self):
        src = (
            "pub fn verify() {}\n"
            "pub struct JwtValidator {}\n"
            "pub enum AuthError {}\n"
            "pub trait Validator {}\n"
        )
        symbols = _extract_symbols_regex(src, ".rs")
        names = {s[1] for s in symbols}
        kinds = {s[0] for s in symbols}
        assert "verify" in names
        assert "JwtValidator" in names
        assert "AuthError" in names
        assert "Validator" in names
        assert {"function", "struct", "enum", "trait"}.issubset(kinds)

    def test_go_symbols(self):
        src = (
            "func alpha() {}\n"
            "type MyStruct struct {}\n"
        )
        symbols = _extract_symbols_regex(src, ".go")
        names = {s[1] for s in symbols}
        assert "alpha" in names
        assert "MyStruct" in names

    def test_typescript_symbols(self):
        src = (
            "export function foo() {}\n"
            "export class Bar {}\n"
            "export interface IFoo {}\n"
            "export type MyType = string;\n"
        )
        symbols = _extract_symbols_regex(src, ".ts")
        names = {s[1] for s in symbols}
        assert "foo" in names
        assert "Bar" in names
        assert "IFoo" in names
        assert "MyType" in names

    def test_unknown_extension(self):
        assert _extract_symbols_regex("whatever", ".xyz") == []


# ── build_summary end-to-end ────────────────────────────────────────────────

class TestBuildSummary:
    def test_summary_contains_file_header(self):
        src = "def foo(): pass\n"
        s = build_summary(
            rel_path="src/main.py",
            content=src,
            ext=".py",
            language="python",
            kind="code",
            top_level_dir="src",
            size=len(src),
            num_chunks=1,
        )
        assert "File: src/main.py" in s.text
        assert "Language: python" in s.text

    def test_summary_contains_symbols_section(self):
        src = (
            "def alpha(): pass\n"
            "def beta(): pass\n"
            "class Gamma: pass\n"
        )
        s = build_summary(
            rel_path="m.py",
            content=src,
            ext=".py",
            language="python",
            kind="code",
            top_level_dir="",
            size=len(src),
            num_chunks=1,
        )
        assert "Symbols:" in s.text
        assert "alpha" in s.text
        assert "Gamma" in s.text
        assert s.symbol_count >= 3

    def test_summary_contains_docstring(self):
        src = '"""Module docstring here."""\n\ndef x(): pass\n'
        s = build_summary(
            rel_path="m.py",
            content=src,
            ext=".py",
            language="python",
            kind="code",
            top_level_dir="",
            size=len(src),
            num_chunks=1,
        )
        assert "Module docstring" in s.text

    def test_summary_includes_imports(self):
        src = "import os\nfrom pathlib import Path\n\ndef x(): pass\n"
        s = build_summary(
            rel_path="m.py",
            content=src,
            ext=".py",
            language="python",
            kind="code",
            top_level_dir="",
            size=len(src),
            num_chunks=1,
        )
        assert "Imports:" in s.text
        assert "import os" in s.text

    def test_summary_truncated_at_max(self):
        src = "x\n" * 10000
        s = build_summary(
            rel_path="big.py",
            content=src,
            ext=".py",
            language="python",
            kind="code",
            top_level_dir="",
            size=len(src),
            num_chunks=50,
        )
        # Summary itself is short because we truncate
        assert len(s.text) <= 2600

    def test_summary_falls_back_to_preview(self):
        # No docstring, no imports, no symbols → should include preview
        src = "x = 1\ny = 2\nz = 3\n"
        s = build_summary(
            rel_path="plain.py",
            content=src,
            ext=".py",
            language="python",
            kind="code",
            top_level_dir="",
            size=len(src),
            num_chunks=1,
        )
        assert "Preview:" in s.text or "Symbols:" in s.text
