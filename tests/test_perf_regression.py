"""
Performance regression tests for large knowledge bases.

Verifies that core operations do not regress beyond acceptable time budgets
when the input size grows. These are NOT micro-benchmarks — they detect
O(n²) regressions or inadvertent blocking I/O introduced into hot paths.

Run with: pytest tests/test_perf_regression.py -v
Marks:    @pytest.mark.slow — skipped in normal CI via `pytest -m "not slow"`
"""

import time
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_fake_add_entry():
    def fake_add_entry(**kwargs):
        return {"entry_id": "fake", "wing": kwargs["wing"], "room": kwargs["room"]}
    return fake_add_entry


def _elapsed(fn):
    """Return (result, seconds_elapsed)."""
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


# ── Miner throughput ─────────────────────────────────────────────────────────

@pytest.mark.slow
class TestMinerThroughput:

    def test_dry_run_200_files_under_5s(self, tmp_path):
        """dry_run mine on 200 small Python files must complete within 5 seconds."""
        src = tmp_path / "src"
        src.mkdir()
        for i in range(200):
            (src / f"module_{i}.py").write_text(
                f"# Module {i}\ndef func_{i}(x):\n    return x + {i}\n"
            )

        from core.auto_init.miner import mine_project
        result, elapsed = _elapsed(
            lambda: mine_project(str(tmp_path), project_slug="perf-test", dry_run=True)
        )

        assert result.files_processed == 200, (
            f"Expected 200 processed, got {result.files_processed}"
        )
        assert elapsed < 5.0, (
            f"dry_run on 200 files took {elapsed:.2f}s — possible O(n²) regression"
        )

    def test_dry_run_500_files_under_15s(self, tmp_path):
        """dry_run mine on 500 files stays under 15 seconds."""
        for subdir in ("api", "core", "tests", "utils", "models"):
            d = tmp_path / subdir
            d.mkdir()
            for i in range(100):
                (d / f"file_{i}.py").write_text(
                    f"class C{i}:\n    val = {i}\n"
                )

        from core.auto_init.miner import mine_project
        result, elapsed = _elapsed(
            lambda: mine_project(str(tmp_path), project_slug="perf-test", dry_run=True)
        )

        assert result.files_processed == 500
        assert elapsed < 15.0, (
            f"dry_run on 500 files took {elapsed:.2f}s"
        )

    def test_mine_200_files_with_mock_palace_under_8s(self, tmp_path):
        """Mine (with mock palace) on 200 files must complete within 8 seconds."""
        src = tmp_path / "src"
        src.mkdir()
        for i in range(200):
            (src / f"mod_{i}.py").write_text(f"x = {i}\n" * 10)

        with patch("core.palace.add_entry", _make_fake_add_entry()):
            from core.auto_init.miner import mine_project
            result, elapsed = _elapsed(
                lambda: mine_project(str(tmp_path), project_slug="perf-test")
            )

        assert result.files_processed == 200
        assert elapsed < 8.0, (
            f"mine on 200 files with mock palace took {elapsed:.2f}s"
        )

    def test_large_single_file_under_2s(self, tmp_path):
        """A single large file (near MAX_FILE_SIZE) is chunked and processed quickly."""
        from core.auto_init.miner import MAX_FILE_SIZE

        large_file = tmp_path / "big_module.py"
        # Write a file just under the size limit
        line = "x = 1  # padding\n"
        content = line * (MAX_FILE_SIZE // len(line.encode()))
        large_file.write_text(content)

        from core.auto_init.miner import mine_project
        result, elapsed = _elapsed(
            lambda: mine_project(str(tmp_path), project_slug="perf-test", dry_run=True)
        )

        assert result.files_processed == 1
        assert elapsed < 2.0, (
            f"Processing a large single file took {elapsed:.2f}s"
        )


# ── Chunker throughput ───────────────────────────────────────────────────────

class TestChunkerThroughput:

    def test_chunk_10k_line_file_under_1s(self):
        """Chunking a 10,000-line file must complete in under 1 second."""
        from core.auto_init.miner import _chunks

        content = "def func(x):\n    return x + 1\n" * 5000  # ~10k lines
        _, elapsed = _elapsed(lambda: _chunks("big.py", content))
        assert elapsed < 1.0, f"Chunking 10k-line file took {elapsed:.2f}s"

    def test_chunk_1000_files_sequentially_under_3s(self):
        """Chunking 1,000 small files sequentially completes under 3 seconds."""
        from core.auto_init.miner import _chunks

        content = "x = 1\n" * 50  # Small but non-trivial

        def run():
            for i in range(1000):
                _chunks(f"file{i}.py", content)

        _, elapsed = _elapsed(run)
        assert elapsed < 3.0, f"1000 sequential chunk calls took {elapsed:.2f}s"


# ── Search retrieval throughput ──────────────────────────────────────────────

class TestSearchThroughput:

    def test_search_with_100_mock_results_formats_under_1s(self):
        """Formatting 100 search results in a tool response must be fast."""
        import asyncio
        from core.rag.retriever import RetrievalResult

        mock_results = [
            RetrievalResult(
                content=f"Entry {i}: some meaningful technical content about system design",
                collection=f"code-module{i % 10}",
                entry_id=f"entry-{i:04d}",
                relevance_score=round(0.5 + (i % 50) / 100, 2),
                metadata={"source_file": f"src/module_{i}.py"},
            )
            for i in range(100)
        ]

        with patch("mcp_server.tools.memory_tools._search", return_value=mock_results):
            from mcp_server.tools.memory_tools import search_memory

            def run():
                return asyncio.get_event_loop().run_until_complete(
                    search_memory("system design")
                )

            result, elapsed = _elapsed(run)

        assert elapsed < 1.0, f"Formatting 100 results took {elapsed:.2f}s"
        assert isinstance(result, str)
        assert len(result) > 0


# ── File discovery throughput ────────────────────────────────────────────────

@pytest.mark.slow
class TestDiscoveryThroughput:

    def test_discover_500_files_under_3s(self, tmp_path):
        """_discover_files on 500 files should complete under 3 seconds."""
        for i in range(500):
            subdir = tmp_path / f"pkg{i % 10}"
            subdir.mkdir(exist_ok=True)
            (subdir / f"mod_{i}.py").write_text(f"x = {i}")

        from core.auto_init.miner import _discover_files
        from core.auto_init.miner_config import MinerConfig

        config = MinerConfig()
        skip_reasons: dict = {}

        _, elapsed = _elapsed(lambda: _discover_files(tmp_path, config, skip_reasons=skip_reasons))
        assert elapsed < 3.0, f"File discovery on 500 files took {elapsed:.2f}s"

    def test_skip_dirs_are_pruned_not_traversed(self, tmp_path):
        """node_modules with 1000 files should be skipped, not traversed."""
        node_mods = tmp_path / "node_modules"
        node_mods.mkdir()
        for i in range(1000):
            (node_mods / f"lib_{i}.js").write_text(f"module.exports = {i};")

        (tmp_path / "index.py").write_text("x = 1")

        from core.auto_init.miner import _discover_files
        from core.auto_init.miner_config import MinerConfig

        config = MinerConfig()
        skip_reasons: dict = {}

        files, elapsed = _elapsed(lambda: _discover_files(tmp_path, config, skip_reasons=skip_reasons))
        # Only index.py should be discovered — node_modules pruned
        assert len(files) == 1
        # Should be fast because node_modules is pruned, not walked
        assert elapsed < 1.0, f"Discovery with pruned skip dir took {elapsed:.2f}s"
