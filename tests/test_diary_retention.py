"""Tests for diary retention cap (Gap 4 fix)."""

from unittest.mock import patch, MagicMock

import pytest

from core.palace import _prune_diary, DIARY_MAX_ENTRIES, diary_write


class TestPruneDiary:
    """Unit tests for _prune_diary — oldest-first deletion beyond the cap."""

    def test_no_prune_when_under_limit(self):
        """Nothing deleted when total diary entries <= DIARY_MAX_ENTRIES."""
        mock_col = MagicMock()
        mock_col.get.return_value = {
            "ids": [f"diary_{i}" for i in range(10)],
            "metadatas": [{"filed_at": f"2026-04-{i+1:02d}T00:00:00"} for i in range(10)],
        }

        with patch("core.palace._mp_mcp") as mp:
            mp._get_collection.return_value = mock_col
            pruned = _prune_diary("copilot")

        assert pruned == 0
        mock_col.delete.assert_not_called()

    def test_prune_oldest_beyond_cap(self):
        """Entries beyond the cap are deleted, oldest first."""
        cap = DIARY_MAX_ENTRIES
        total = cap + 5
        ids = [f"diary_{i}" for i in range(total)]
        metas = [{"filed_at": f"2026-01-01T{i:02d}:00:00"} for i in range(total)]

        mock_col = MagicMock()
        mock_col.get.return_value = {"ids": ids, "metadatas": metas}

        with patch("core.palace._mp_mcp") as mp:
            mp._get_collection.return_value = mock_col
            pruned = _prune_diary("copilot")

        assert pruned == 5
        deleted_ids = mock_col.delete.call_args[1]["ids"]
        # Should delete the 5 oldest (lowest filed_at)
        assert len(deleted_ids) == 5
        assert deleted_ids == ids[:5]

    def test_no_collection_returns_zero(self):
        """Gracefully returns 0 when no collection available."""
        with patch("core.palace._mp_mcp") as mp:
            mp._get_collection.return_value = None
            assert _prune_diary("copilot") == 0

    def test_exception_returns_zero(self):
        """Gracefully returns 0 when collection.get() raises."""
        mock_col = MagicMock()
        mock_col.get.side_effect = RuntimeError("db error")

        with patch("core.palace._mp_mcp") as mp:
            mp._get_collection.return_value = mock_col
            assert _prune_diary("copilot") == 0


class TestDiaryWriteTriggersPrune:
    """diary_write should call _prune_diary after a successful write."""

    @patch("core.palace._prune_diary")
    @patch("core.palace.tool_diary_write")
    def test_prune_called_on_success(self, mock_write, mock_prune):
        mock_write.return_value = {"success": True, "entry_id": "x"}
        diary_write("copilot", "test entry")
        mock_prune.assert_called_once_with("copilot")

    @patch("core.palace._prune_diary")
    @patch("core.palace.tool_diary_write")
    def test_prune_not_called_on_failure(self, mock_write, mock_prune):
        mock_write.return_value = {"success": False, "error": "bad"}
        diary_write("copilot", "test entry")
        mock_prune.assert_not_called()
