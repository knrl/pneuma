"""Tests for core/auto_init — project analyzer and layout generation."""

from pathlib import Path

import pytest

from core.auto_init.analyzer import analyze_project
from core.auto_init.templates import build_template, slugify_room


# ── Analyzer ─────────────────────────────────────────────────────

class TestAnalyzeProject:
    def _make_tree(self, tmp: str, files: list[str]):
        for f in files:
            p = Path(tmp) / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("")

    def test_detects_python(self, tmp_path):
        self._make_tree(str(tmp_path), ["app.py", "utils.py"])
        profile = analyze_project(str(tmp_path))
        assert "python" in profile.languages
        assert profile.languages["python"] == 2

    def test_detects_multiple_languages(self, tmp_path):
        self._make_tree(str(tmp_path), ["app.py", "index.js", "main.ts"])
        profile = analyze_project(str(tmp_path))
        assert "python" in profile.languages
        assert "javascript" in profile.languages
        assert "typescript" in profile.languages

    def test_detects_framework_markers(self, tmp_path):
        self._make_tree(str(tmp_path), ["pyproject.toml", "Dockerfile"])
        profile = analyze_project(str(tmp_path))
        assert "python-project" in profile.frameworks
        assert "docker" in profile.frameworks

    def test_skips_ignored_dirs(self, tmp_path):
        self._make_tree(str(tmp_path), [
            "src/app.py",
            "node_modules/lodash/index.js",
            "__pycache__/mod.pyc",
        ])
        profile = analyze_project(str(tmp_path))
        assert profile.languages.get("javascript", 0) == 0

    def test_complexity_small(self, tmp_path):
        self._make_tree(str(tmp_path), [f"f{i}.py" for i in range(10)])
        profile = analyze_project(str(tmp_path))
        assert profile.complexity == "small"

    def test_complexity_medium(self, tmp_path):
        self._make_tree(str(tmp_path), [f"f{i}.py" for i in range(150)])
        profile = analyze_project(str(tmp_path))
        assert profile.complexity == "medium"

    def test_complexity_large(self, tmp_path):
        self._make_tree(str(tmp_path), [f"f{i}.py" for i in range(600)])
        profile = analyze_project(str(tmp_path))
        assert profile.complexity == "large"

    def test_nonexistent_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            analyze_project("/nonexistent/path/xyz")

    def test_empty_dir(self, tmp_path):
        profile = analyze_project(str(tmp_path))
        assert profile.languages == {}
        assert profile.total_files == 0
        assert profile.complexity == "small"

    def test_detects_top_level_dirs(self, tmp_path):
        self._make_tree(str(tmp_path), [
            "src/app.py",
            "tests/test_app.py",
            "docs/readme.md",
            "README.md",
        ])
        profile = analyze_project(str(tmp_path))
        assert "src" in profile.top_level_dirs
        assert "tests" in profile.top_level_dirs
        assert "docs" in profile.top_level_dirs

    def test_top_level_dirs_excludes_hidden_and_skip(self, tmp_path):
        self._make_tree(str(tmp_path), [
            "src/app.py",
            ".git/config",
            "node_modules/lodash/index.js",
            ".hidden/file.txt",
        ])
        profile = analyze_project(str(tmp_path))
        assert "src" in profile.top_level_dirs
        assert ".git" not in profile.top_level_dirs
        assert "node_modules" not in profile.top_level_dirs
        assert ".hidden" not in profile.top_level_dirs


# ── Slugification ────────────────────────────────────────────────

class TestSlugifyRoom:
    def test_lowercase(self):
        assert slugify_room("SrcDir") == "srcdir"

    def test_preserves_underscores_and_hyphens(self):
        assert slugify_room("rust_ffi") == "rust_ffi"
        assert slugify_room("vs2026-projects") == "vs2026-projects"

    def test_replaces_spaces_and_dots(self):
        assert slugify_room("My Folder") == "my-folder"
        assert slugify_room("my.app.v2") == "my-app-v2"

    def test_strips_leading_trailing_hyphens(self):
        assert slugify_room("--dir--") == "dir"

    def test_empty_falls_back_to_general(self):
        assert slugify_room("") == "general"
        assert slugify_room("---") == "general"


# ── Templates ────────────────────────────────────────────────────

class TestBuildTemplate:
    def test_has_two_wings(self):
        t = build_template("small", project_slug="myapp", top_level_dirs=["src"])
        names = [w.name for w in t.wings]
        assert "code" in names
        assert "chat" in names
        assert len(names) == 2

    def test_code_wing_always_named_code(self):
        t = build_template("small", project_slug="my-app", top_level_dirs=["src"])
        assert t.wings[0].name == "code"

    def test_project_wing_rooms_from_dirs(self):
        t = build_template(
            "large",
            project_slug="myproj",
            top_level_dirs=["src", "tests", "docs", "rust_ffi"],
        )
        code_wing = next(w for w in t.wings if w.name == "code")
        room_names = [r.name for r in code_wing.rooms]
        assert "src" in room_names
        assert "tests" in room_names   # canonical
        assert "docs" in room_names    # canonical
        assert "rust_ffi" in room_names
        assert "general" in room_names  # always added

    def test_empty_top_level_dirs_still_has_general(self):
        t = build_template("small", project_slug="myapp", top_level_dirs=[])
        code_wing = next(w for w in t.wings if w.name == "code")
        room_names = [r.name for r in code_wing.rooms]
        assert room_names == ["general"]

    def test_duplicate_slugs_deduplicated(self):
        t = build_template(
            "small",
            project_slug="myapp",
            top_level_dirs=["My-Dir", "my dir"],  # both slugify to "my-dir"
        )
        code_wing = next(w for w in t.wings if w.name == "code")
        room_names = [r.name for r in code_wing.rooms]
        assert room_names.count("my-dir") == 1

    def test_label_contains_complexity(self):
        assert "large" in build_template("large", project_slug="x").label
        assert "small" in build_template("small", project_slug="x").label

    def test_chat_wing_has_six_rooms(self):
        t = build_template("small", project_slug="myapp", top_level_dirs=["src"])
        chat = next(w for w in t.wings if w.name == "chat")
        room_names = [r.name for r in chat.rooms]
        assert len(room_names) == 6
        assert "decisions" in room_names
        assert "conventions" in room_names
        assert "solutions" in room_names
        assert "workarounds" in room_names
        assert "escalations" in room_names
        assert "context" in room_names
