"""Tests for core/auto_init/miner — directory routing, metadata, chunking."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ── Routing ──────────────────────────────────────────────────────────────────

class TestRoutingByPath:

    def test_top_level_file_routes_to_general(self):
        from core.auto_init.miner import _route_by_path
        assert _route_by_path("README.md") == ("code", "general")

    def test_nested_file_routes_to_top_dir(self):
        from core.auto_init.miner import _route_by_path
        assert _route_by_path("src/auth/jwt.rs") == ("code", "src")

    def test_top_dir_is_slugified(self):
        from core.auto_init.miner import _route_by_path
        assert _route_by_path("Rust FFI/mod.rs") == ("code", "rust-ffi")

    def test_dot_dirs_stay(self):
        from core.auto_init.miner import _route_by_path
        # dots become hyphens via slugify
        assert _route_by_path("vs2026.projects/main.cpp")[1] == "vs2026-projects"

    def test_canonical_tests_dir(self):
        from core.auto_init.miner import _route_by_path
        assert _route_by_path("tests/test_auth.py") == ("code", "tests")
        assert _route_by_path("test/unit.py") == ("code", "tests")
        assert _route_by_path("spec/parser_spec.rb") == ("code", "tests")

    def test_canonical_docs_dir(self):
        from core.auto_init.miner import _route_by_path
        assert _route_by_path("docs/readme.md") == ("code", "docs")
        assert _route_by_path("doc/api.md") == ("code", "docs")

    def test_windows_backslash_paths(self):
        from core.auto_init.miner import _route_by_path
        # pathlib normalizes these on Windows
        rel = str(Path("src/auth/jwt.rs"))
        wing, room = _route_by_path(rel)
        assert wing == "code"
        assert room == "src"


# ── Kind classification ──────────────────────────────────────────────────────

class TestKindClassification:

    def test_code_file(self):
        from core.auto_init.miner import _classify_kind
        assert _classify_kind("src/main.rs", ".rs") == "code"

    def test_test_file_in_tests_dir(self):
        from core.auto_init.miner import _classify_kind
        assert _classify_kind("tests/test_auth.py", ".py") == "test"

    def test_test_file_by_suffix(self):
        from core.auto_init.miner import _classify_kind
        assert _classify_kind("src/auth_test.go", ".go") == "test"

    def test_spec_file(self):
        from core.auto_init.miner import _classify_kind
        assert _classify_kind("spec/parser_spec.rb", ".rb") == "test"

    def test_doc(self):
        from core.auto_init.miner import _classify_kind
        assert _classify_kind("README.md", ".md") == "doc"

    def test_config(self):
        from core.auto_init.miner import _classify_kind
        assert _classify_kind("config.yaml", ".yaml") == "config"
        assert _classify_kind("app.toml", ".toml") == "config"

    def test_script(self):
        from core.auto_init.miner import _classify_kind
        assert _classify_kind("scripts/build.sh", ".sh") == "script"


# ── Language detection ──────────────────────────────────────────────────────

class TestLanguageDetection:

    def test_known_extensions(self):
        from core.auto_init.miner import _LANG_FROM_EXT
        assert _LANG_FROM_EXT[".rs"] == "rust"
        assert _LANG_FROM_EXT[".py"] == "python"
        assert _LANG_FROM_EXT[".cpp"] == "cpp"
        assert _LANG_FROM_EXT[".md"] == "markdown"


# ── Metadata builder ────────────────────────────────────────────────────────

class TestBuildMetadata:

    def test_contains_all_expected_keys(self):
        from core.auto_init.miner import _build_metadata

        meta = _build_metadata(
            rel_path="src/auth/jwt.rs",
            ext=".rs",
            content="pub fn verify() {}",
            mtime=1714060800.0,
            size=20,
            chunk_idx=1,
            total_chunks=1,
            top_level_dir="src",
        )
        for key in ("source_file", "language", "kind", "top_level_dir",
                    "mtime", "size", "content_hash", "chunk_index", "total_chunks"):
            assert key in meta

    def test_language_from_extension(self):
        from core.auto_init.miner import _build_metadata

        meta = _build_metadata(
            rel_path="main.py", ext=".py", content="x=1", mtime=0, size=3,
            chunk_idx=1, total_chunks=1, top_level_dir="",
        )
        assert meta["language"] == "python"

    def test_unknown_extension_returns_unknown(self):
        from core.auto_init.miner import _build_metadata

        meta = _build_metadata(
            rel_path="data.xyz", ext=".xyz", content="", mtime=0, size=0,
            chunk_idx=1, total_chunks=1, top_level_dir="",
        )
        assert meta["language"] == "unknown"

    def test_content_hash_is_stable(self):
        from core.auto_init.miner import _build_metadata

        a = _build_metadata("f.py", ".py", "same content", 0, 12, 1, 1, "")
        b = _build_metadata("f.py", ".py", "same content", 0, 12, 1, 1, "")
        assert a["content_hash"] == b["content_hash"]

    def test_content_hash_changes_with_content(self):
        from core.auto_init.miner import _build_metadata

        a = _build_metadata("f.py", ".py", "content v1", 0, 10, 1, 1, "")
        b = _build_metadata("f.py", ".py", "content v2", 0, 10, 1, 1, "")
        assert a["content_hash"] != b["content_hash"]


# ── Chunking ─────────────────────────────────────────────────────────────────

class TestChunks:

    def test_short_content_single_chunk(self):
        from core.auto_init.miner import _chunks
        result = _chunks("a.py", "short content")
        assert len(result) == 1
        assert "short content" in result[0]
        assert "File: a.py" in result[0]

    def test_long_content_multiple_chunks(self):
        from core.auto_init.miner import _chunks, CHUNK_SIZE
        long_content = "x" * (CHUNK_SIZE * 3)
        chunks = _chunks("big.py", long_content)
        assert len(chunks) >= 3
        for chunk in chunks:
            assert "File: big.py" in chunk

    def test_chunks_have_part_numbers_when_split(self):
        from core.auto_init.miner import _chunks, CHUNK_SIZE
        long_content = "y" * (CHUNK_SIZE * 2 + 100)
        chunks = _chunks("big.py", long_content)
        assert any("part 1" in c for c in chunks)
        assert any("part 2" in c for c in chunks)


# ── Integration: mine_project with mocked palace ──────────────────────────────

class TestMineProject:

    def test_routes_files_to_correct_rooms(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "tests" / "test_main.py").write_text("def test_x(): pass")
        (tmp_path / "README.md").write_text("# docs")

        captured = []

        def fake_add_entry(**kwargs):
            captured.append((kwargs["wing"], kwargs["room"]))
            return {"entry_id": "fake", "wing": kwargs["wing"], "room": kwargs["room"]}

        from core.auto_init import miner

        with patch.object(miner, "add_entry", fake_add_entry, create=True):
            with patch("core.palace.add_entry", fake_add_entry):
                result = miner.mine_project(str(tmp_path), project_slug="myapp")

        wings = {w for w, _ in captured}
        rooms = {r for _, r in captured}
        assert wings == {"code"}
        assert "src" in rooms
        assert "tests" in rooms
        assert "general" in rooms
        assert result.files_processed == 3

    def test_skips_binary_extensions(self, tmp_path):
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n")
        (tmp_path / "main.py").write_text("x = 1")

        def fake_add_entry(**kwargs):
            return {"entry_id": "fake", "wing": kwargs["wing"], "room": kwargs["room"]}

        with patch("core.palace.add_entry", fake_add_entry):
            from core.auto_init.miner import mine_project
            result = mine_project(str(tmp_path), project_slug="myapp")

        assert result.files_processed == 1
        assert result.files_skipped >= 1

    def test_skips_lockfiles(self, tmp_path):
        (tmp_path / "package-lock.json").write_text("{}")
        (tmp_path / "main.py").write_text("x = 1")

        def fake_add_entry(**kwargs):
            return {"entry_id": "fake", "wing": kwargs["wing"], "room": kwargs["room"]}

        with patch("core.palace.add_entry", fake_add_entry):
            from core.auto_init.miner import mine_project
            result = mine_project(str(tmp_path), project_slug="myapp")

        assert result.files_processed == 1

    def test_skips_ignored_dirs(self, tmp_path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lib.js").write_text("x")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1")

        def fake_add_entry(**kwargs):
            return {"entry_id": "fake", "wing": kwargs["wing"], "room": kwargs["room"]}

        with patch("core.palace.add_entry", fake_add_entry):
            from core.auto_init.miner import mine_project
            result = mine_project(str(tmp_path), project_slug="myapp")

        assert result.files_processed == 1

    def test_metadata_is_passed_to_palace(self, tmp_path):
        (tmp_path / "app.py").write_text("print('hi')")

        captured_meta = []

        def fake_add_entry(**kwargs):
            captured_meta.append(kwargs.get("metadata", {}))
            return {"entry_id": "fake", "wing": kwargs["wing"], "room": kwargs["room"]}

        with patch("core.palace.add_entry", fake_add_entry):
            from core.auto_init.miner import mine_project
            mine_project(str(tmp_path), project_slug="myapp")

        assert captured_meta
        meta = captured_meta[0]
        assert meta["language"] == "python"
        assert meta["kind"] == "code"
        assert meta["source_file"] == "app.py"
        assert "content_hash" in meta


# ── Dry run ──────────────────────────────────────────────────────────────────

class TestDryRun:

    def test_dry_run_does_not_call_add_entry(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hi')")
        (tmp_path / "README.md").write_text("# docs")

        from core.auto_init.miner import mine_project

        # No patching — if add_entry is called, it will fail because palace
        # isn't configured. That's the test.
        result = mine_project(str(tmp_path), project_slug="myapp", dry_run=True)

        assert result.files_processed == 2
        assert result.chunks_stored >= 2
        assert result.summaries_stored == 2
        assert result.would_route
        assert not result.errors

    def test_dry_run_populates_would_route(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "a.py").write_text("x = 1")
        (tmp_path / "tests" / "b.py").write_text("y = 2")

        from core.auto_init.miner import mine_project
        result = mine_project(str(tmp_path), project_slug="myapp", dry_run=True)

        assert "code/src" in result.would_route
        assert "code/tests" in result.would_route

    def test_dry_run_populates_skip_reasons(self, tmp_path):
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        (tmp_path / "package-lock.json").write_text("{}")
        (tmp_path / "app.py").write_text("x = 1")

        from core.auto_init.miner import mine_project
        result = mine_project(str(tmp_path), project_slug="myapp", dry_run=True)

        # Both binary and lockfile should show up in skip_reasons
        assert "binary" in result.skip_reasons
        assert "lockfile-or-os" in result.skip_reasons

    def test_dry_run_skips_generated_files(self, tmp_path):
        (tmp_path / "service.pb.go").write_text("generated code")
        (tmp_path / "main.go").write_text("package main")

        from core.auto_init.miner import mine_project
        result = mine_project(str(tmp_path), project_slug="myapp", dry_run=True)

        assert result.files_processed == 1  # only main.go
        assert result.skip_reasons.get("generated", 0) >= 1
