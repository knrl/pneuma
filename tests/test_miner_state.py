"""Tests for core/auto_init/miner_state — SQLite state tracking for
incremental re-mining."""

import pytest
from unittest.mock import patch

from core.auto_init.miner_state import MiningState, compute_content_hash


# ── compute_content_hash ─────────────────────────────────────────────────────

class TestComputeHash:
    def test_stable(self):
        assert compute_content_hash("abc") == compute_content_hash("abc")

    def test_changes_with_content(self):
        assert compute_content_hash("abc") != compute_content_hash("abd")

    def test_returns_16_chars(self):
        h = compute_content_hash("some content")
        assert len(h) == 16

    def test_handles_unicode(self):
        h = compute_content_hash("héllo wörld")
        assert isinstance(h, str)
        assert len(h) == 16


# ── MiningState ──────────────────────────────────────────────────────────────

class TestMiningState:
    def test_creates_db_file(self, tmp_path):
        state = MiningState(str(tmp_path))
        assert (tmp_path / "mined_files.sqlite3").exists()
        state.close()

    def test_upsert_and_get(self, tmp_path):
        with MiningState(str(tmp_path)) as state:
            state.upsert("src/main.py", "abc123", 1714060800.0, ["eid-1", "eid-2"])
            rec = state.get("src/main.py")
            assert rec is not None
            assert rec.content_hash == "abc123"
            assert rec.mtime == 1714060800.0
            assert rec.entry_ids == ["eid-1", "eid-2"]

    def test_get_missing_returns_none(self, tmp_path):
        with MiningState(str(tmp_path)) as state:
            assert state.get("nonexistent.py") is None

    def test_upsert_replaces_existing(self, tmp_path):
        with MiningState(str(tmp_path)) as state:
            state.upsert("f.py", "hash1", 1.0, ["e1"])
            state.upsert("f.py", "hash2", 2.0, ["e2", "e3"])
            rec = state.get("f.py")
            assert rec.content_hash == "hash2"
            assert rec.entry_ids == ["e2", "e3"]

    def test_has_changed_new_file(self, tmp_path):
        with MiningState(str(tmp_path)) as state:
            assert state.has_changed("new.py", "hash")

    def test_has_changed_same_hash(self, tmp_path):
        with MiningState(str(tmp_path)) as state:
            state.upsert("f.py", "h", 0.0, ["e"])
            assert not state.has_changed("f.py", "h")

    def test_has_changed_different_hash(self, tmp_path):
        with MiningState(str(tmp_path)) as state:
            state.upsert("f.py", "h1", 0.0, ["e"])
            assert state.has_changed("f.py", "h2")

    def test_delete(self, tmp_path):
        with MiningState(str(tmp_path)) as state:
            state.upsert("f.py", "h", 0.0, ["e"])
            state.delete("f.py")
            assert state.get("f.py") is None

    def test_all_paths(self, tmp_path):
        with MiningState(str(tmp_path)) as state:
            state.upsert("a.py", "h1", 0.0, ["e1"])
            state.upsert("b.py", "h2", 0.0, ["e2"])
            state.upsert("c.py", "h3", 0.0, ["e3"])
            paths = state.all_paths()
            assert paths == {"a.py", "b.py", "c.py"}

    def test_all_records(self, tmp_path):
        with MiningState(str(tmp_path)) as state:
            state.upsert("a.py", "h1", 1.0, ["e1", "e2"])
            state.upsert("b.py", "h2", 2.0, ["e3"])
            records = state.all_records()
            assert len(records) == 2
            by_path = {r.rel_path: r for r in records}
            assert by_path["a.py"].entry_ids == ["e1", "e2"]
            assert by_path["b.py"].entry_ids == ["e3"]

    def test_persists_across_instances(self, tmp_path):
        s1 = MiningState(str(tmp_path))
        s1.upsert("persistent.py", "h", 0.0, ["e"])
        s1.close()

        s2 = MiningState(str(tmp_path))
        rec = s2.get("persistent.py")
        assert rec is not None
        assert rec.content_hash == "h"
        s2.close()


# ── Incremental integration with mine_project ───────────────────────────────

class TestIncrementalMining:
    def _setup_palace(self, tmp_path, monkeypatch):
        """Register a fake project and point registry/palace at tmp dirs."""
        palace_dir = tmp_path / "palace"
        palace_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        def fake_get_project(path):
            return {
                "slug": "myproj",
                "palace_dir": str(palace_dir),
                "palace_path": str(palace_dir / "palace"),
                "kg_path": str(palace_dir / "kg.sqlite"),
                "project_path": str(project_dir),
            }

        monkeypatch.setattr("core.registry.get_project", fake_get_project)
        return project_dir, palace_dir

    def test_unchanged_file_skipped_on_second_run(self, tmp_path, monkeypatch):
        project_dir, palace_dir = self._setup_palace(tmp_path, monkeypatch)
        (project_dir / "src").mkdir()
        (project_dir / "src" / "main.py").write_text("x = 1")

        call_count = {"n": 0}

        def fake_add_entry(**kwargs):
            call_count["n"] += 1
            return {"entry_id": f"eid-{call_count['n']}", "wing": kwargs["wing"], "room": kwargs["room"]}

        from core.auto_init import miner

        with patch("core.palace.add_entry", fake_add_entry):
            with patch("core.palace.delete_entry", lambda *a, **k: {"success": True}):
                # First run — fresh, everything mined
                r1 = miner.mine_project(str(project_dir), incremental=True)
                assert r1.files_processed == 1
                calls_after_first = call_count["n"]

                # Second run — same content, nothing changed
                r2 = miner.mine_project(str(project_dir), incremental=True)
                assert r2.files_unchanged == 1
                assert r2.files_processed == 0
                # add_entry should not have been called again
                assert call_count["n"] == calls_after_first

    def test_changed_file_re_mined(self, tmp_path, monkeypatch):
        project_dir, palace_dir = self._setup_palace(tmp_path, monkeypatch)
        (project_dir / "main.py").write_text("x = 1")

        deleted_ids: list[str] = []

        def fake_add_entry(**kwargs):
            return {"entry_id": f"eid-{id(kwargs)}", "wing": kwargs["wing"], "room": kwargs["room"]}

        def fake_delete(eid):
            deleted_ids.append(eid)
            return {"success": True}

        from core.auto_init import miner

        with patch("core.palace.add_entry", fake_add_entry):
            with patch("core.palace.delete_entry", fake_delete):
                miner.mine_project(str(project_dir), incremental=True)

                # Change the file
                (project_dir / "main.py").write_text("x = 999  # changed")

                r = miner.mine_project(str(project_dir), incremental=True)
                assert r.files_processed == 1
                assert r.files_unchanged == 0
                # Old entry IDs should have been deleted
                assert len(deleted_ids) >= 1

    def test_removed_file_cleans_up(self, tmp_path, monkeypatch):
        project_dir, palace_dir = self._setup_palace(tmp_path, monkeypatch)
        (project_dir / "a.py").write_text("x = 1")
        (project_dir / "b.py").write_text("y = 2")

        deleted_ids: list[str] = []

        def fake_add_entry(**kwargs):
            return {"entry_id": f"eid-{id(kwargs)}", "wing": kwargs["wing"], "room": kwargs["room"]}

        def fake_delete(eid):
            deleted_ids.append(eid)
            return {"success": True}

        from core.auto_init import miner

        with patch("core.palace.add_entry", fake_add_entry):
            with patch("core.palace.delete_entry", fake_delete):
                miner.mine_project(str(project_dir), incremental=True)

                # Remove a.py
                (project_dir / "a.py").unlink()

                r = miner.mine_project(str(project_dir), incremental=True)
                assert r.files_removed == 1
                # Deleted IDs should include a.py's entries
                assert len(deleted_ids) >= 1
