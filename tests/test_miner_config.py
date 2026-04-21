"""Tests for core/auto_init/miner_config — config loading and pattern matching."""

import json
from pathlib import Path

import pytest

from core.auto_init.miner_config import (
    MinerConfig,
    load_config,
    _match_gitignore,
)


# ── Defaults ─────────────────────────────────────────────────────────────────

class TestMinerConfigDefaults:
    def test_default_chunk_size(self):
        cfg = MinerConfig()
        assert cfg.chunk_size == 1500
        assert cfg.chunk_overlap == 150

    def test_default_max_file_size(self):
        cfg = MinerConfig()
        assert cfg.max_file_size == 100_000

    def test_default_generated_patterns_include_protobuf(self):
        cfg = MinerConfig()
        assert "*.pb.go" in cfg.generated_patterns
        assert "*.min.js" in cfg.generated_patterns


# ── is_generated ────────────────────────────────────────────────────────────

class TestIsGenerated:
    def test_detects_protobuf_output(self):
        cfg = MinerConfig()
        assert cfg.is_generated("service.pb.go")
        assert cfg.is_generated("messages.pb.py")

    def test_detects_minified(self):
        cfg = MinerConfig()
        assert cfg.is_generated("app.min.js")
        assert cfg.is_generated("bundle.min.css")

    def test_detects_source_maps(self):
        cfg = MinerConfig()
        assert cfg.is_generated("app.js.map")

    def test_regular_file_not_generated(self):
        cfg = MinerConfig()
        assert not cfg.is_generated("main.py")
        assert not cfg.is_generated("app.rs")


# ── is_skipped ──────────────────────────────────────────────────────────────

class TestIsSkipped:
    def test_matches_simple_directory_pattern(self):
        cfg = MinerConfig(extra_skip=["third_party/**"])
        assert cfg.is_skipped("third_party/lib/foo.py")
        assert not cfg.is_skipped("src/main.py")

    def test_matches_glob_pattern(self):
        cfg = MinerConfig(extra_skip=["**/*_generated.*"])
        assert cfg.is_skipped("src/api/client_generated.py")

    def test_gitignore_patterns_applied(self):
        cfg = MinerConfig()
        cfg.gitignore_patterns = ["target/", "*.lock"]
        assert cfg.is_skipped("target/release/app")
        # *.lock should match Cargo.lock anywhere
        assert cfg.is_skipped("Cargo.lock")


# ── Gitignore-style glob matching ───────────────────────────────────────────

class TestGitignoreMatch:
    def test_simple_filename(self):
        assert _match_gitignore("Cargo.lock", "Cargo.lock")
        assert _match_gitignore("src/Cargo.lock", "Cargo.lock")  # unanchored

    def test_anchored_pattern(self):
        assert _match_gitignore("Cargo.lock", "/Cargo.lock")
        assert not _match_gitignore("src/Cargo.lock", "/Cargo.lock")

    def test_directory_pattern(self):
        assert _match_gitignore("target/release/app", "target/")
        assert _match_gitignore("node_modules/lodash/index.js", "node_modules/")

    def test_double_star_any_depth(self):
        assert _match_gitignore("src/deep/nested/path/file.py", "**/file.py")
        assert _match_gitignore("a/b/c/generated.rs", "**/*_generated.*") is False
        assert _match_gitignore("a/b/c/foo_generated.rs", "**/*_generated.*")

    def test_extension_glob(self):
        assert _match_gitignore("app.log", "*.log")
        assert _match_gitignore("deep/path/app.log", "*.log")

    def test_does_not_match_unrelated(self):
        assert not _match_gitignore("src/main.rs", "tests/")
        assert not _match_gitignore("app.py", "*.rs")


# ── priority_rank ───────────────────────────────────────────────────────────

class TestPriorityRank:
    def test_higher_priority_returns_lower_rank(self):
        cfg = MinerConfig(priority=["README.md", "docs/**", "src/**"])
        assert cfg.priority_rank("README.md") == 0
        assert cfg.priority_rank("docs/intro.md") == 1
        assert cfg.priority_rank("src/main.py") == 2

    def test_unmatched_gets_large_rank(self):
        cfg = MinerConfig(priority=["README.md"])
        rank = cfg.priority_rank("random.py")
        assert rank > 100


# ── load_config ─────────────────────────────────────────────────────────────

class TestLoadConfig:
    def test_no_config_file_returns_defaults(self, tmp_path):
        cfg = load_config(str(tmp_path))
        assert cfg.chunk_size == 1500
        assert cfg.extra_skip == []

    def test_loads_json_config(self, tmp_path):
        (tmp_path / ".pneuma.json").write_text(json.dumps({
            "miner": {
                "chunk_size": 3000,
                "skip": ["third_party/**"],
                "priority": ["README.md"],
            }
        }))
        cfg = load_config(str(tmp_path))
        assert cfg.chunk_size == 3000
        assert "third_party/**" in cfg.extra_skip
        assert cfg.priority == ["README.md"]

    def test_loads_json_without_miner_key(self, tmp_path):
        (tmp_path / ".pneuma.json").write_text(json.dumps({
            "chunk_size": 2000,
        }))
        cfg = load_config(str(tmp_path))
        assert cfg.chunk_size == 2000

    def test_malformed_json_falls_back_to_defaults(self, tmp_path):
        (tmp_path / ".pneuma.json").write_text("{ this is not json")
        cfg = load_config(str(tmp_path))
        # Should not raise, just use defaults
        assert cfg.chunk_size == 1500

    def test_loads_gitignore_patterns(self, tmp_path):
        (tmp_path / ".gitignore").write_text(
            "# comment\n"
            "target/\n"
            "*.log\n"
            "\n"
            "!important.log\n"  # negation, should be dropped
        )
        cfg = load_config(str(tmp_path))
        assert "target/" in cfg.gitignore_patterns
        assert "*.log" in cfg.gitignore_patterns
        assert "!important.log" not in cfg.gitignore_patterns

    def test_respect_gitignore_false_skips_loading(self, tmp_path):
        (tmp_path / ".gitignore").write_text("target/\n")
        (tmp_path / ".pneuma.json").write_text(json.dumps({
            "miner": {"respect_gitignore": False}
        }))
        cfg = load_config(str(tmp_path))
        assert cfg.gitignore_patterns == []

    def test_yaml_loaded_if_pyyaml_available(self, tmp_path):
        pytest.importorskip("yaml")
        (tmp_path / ".pneuma.yaml").write_text(
            "miner:\n"
            "  chunk_size: 2500\n"
            "  skip:\n"
            "    - third_party/**\n"
        )
        cfg = load_config(str(tmp_path))
        assert cfg.chunk_size == 2500
        assert "third_party/**" in cfg.extra_skip

    def test_user_generated_list_replaces_defaults(self, tmp_path):
        (tmp_path / ".pneuma.json").write_text(json.dumps({
            "miner": {"generated": ["*.custom.js"]}
        }))
        cfg = load_config(str(tmp_path))
        assert cfg.generated_patterns == ["*.custom.js"]
