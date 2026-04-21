"""Tests for retrieval_count bump on search (Gap 6 fix)."""

from unittest.mock import patch, MagicMock, call

import pytest

from core.palace import _bump_retrieval_counts, SearchResult


def _hit(source_file: str, wing: str = "w", room: str = "r", sim: float = 0.9) -> SearchResult:
    return SearchResult(
        content="test content",
        wing=wing,
        room=room,
        similarity=sim,
        source_file=source_file,
        metadata={"source_file": source_file},
    )


class TestBumpRetrievalCounts:
    """Unit tests for _bump_retrieval_counts."""

    def test_increments_count_for_matching_ids(self):
        mock_col = MagicMock()
        mock_col.get.return_value = {
            "ids": ["id1", "id2"],
            "metadatas": [
                {"source_file": "auth.py", "retrieval_count": 0},
                {"source_file": "auth.py", "retrieval_count": 3},
            ],
        }

        with patch("core.palace._mp_mcp") as mp:
            mp._get_collection.return_value = mock_col
            _bump_retrieval_counts([_hit("auth.py")])

        mock_col.update.assert_called_once()
        updated_metas = mock_col.update.call_args[1]["metadatas"]
        assert updated_metas[0]["retrieval_count"] == 1
        assert updated_metas[1]["retrieval_count"] == 4

    def test_skips_unknown_source_files(self):
        """Hits with source_file='?' should not trigger any update."""
        mock_col = MagicMock()

        with patch("core.palace._mp_mcp") as mp:
            mp._get_collection.return_value = mock_col
            _bump_retrieval_counts([_hit("?")])

        mock_col.get.assert_not_called()

    def test_no_collection_is_noop(self):
        with patch("core.palace._mp_mcp") as mp:
            mp._get_collection.return_value = None
            _bump_retrieval_counts([_hit("auth.py")])
            # Should not raise

    def test_handles_missing_retrieval_count(self):
        """Entries with no retrieval_count metadata should default to 0."""
        mock_col = MagicMock()
        mock_col.get.return_value = {
            "ids": ["id1"],
            "metadatas": [{"source_file": "auth.py"}],  # no retrieval_count key
        }

        with patch("core.palace._mp_mcp") as mp:
            mp._get_collection.return_value = mock_col
            _bump_retrieval_counts([_hit("auth.py")])

        updated_metas = mock_col.update.call_args[1]["metadatas"]
        assert updated_metas[0]["retrieval_count"] == 1

    def test_deduplicates_source_files(self):
        """Multiple results with the same source_file only update once."""
        mock_col = MagicMock()
        mock_col.get.return_value = {
            "ids": ["id1"],
            "metadatas": [{"source_file": "auth.py", "retrieval_count": 0}],
        }

        with patch("core.palace._mp_mcp") as mp:
            mp._get_collection.return_value = mock_col
            _bump_retrieval_counts([_hit("auth.py"), _hit("auth.py")])

        # get() should be called only once for the deduplicated source_file
        assert mock_col.get.call_count == 1

    def test_exception_is_swallowed(self):
        """Errors during update should not propagate."""
        mock_col = MagicMock()
        mock_col.get.side_effect = RuntimeError("db error")

        with patch("core.palace._mp_mcp") as mp:
            mp._get_collection.return_value = mock_col
            # Should not raise
            _bump_retrieval_counts([_hit("auth.py")])
