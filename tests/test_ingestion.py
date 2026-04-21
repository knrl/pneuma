"""Tests for core/ingestion/pipeline — inject_entry auto-routing."""

from unittest.mock import patch, MagicMock

import pytest

from core.ingestion.pipeline import inject_entry


class TestInjectEntry:
    @patch("core.ingestion.pipeline.add_entry")
    @patch("core.ingestion.pipeline.route")
    def test_routes_decision_content(self, mock_route, mock_add):
        mock_route.return_value = ("decisions", "architecture")
        mock_add.return_value = {
            "entry_id": "drawer_1",
            "wing": "decisions",
            "room": "architecture",
            "collection": "decisions-architecture",
            "ingested_at": 1000.0,
            "duplicate": False,
        }

        result = inject_entry("We decided to use PostgreSQL")
        assert result["collection"] == "decisions-architecture"
        mock_add.assert_called_once()

    @patch("core.ingestion.pipeline.add_entry")
    @patch("core.ingestion.pipeline.route")
    def test_routes_solution_content(self, mock_route, mock_add):
        mock_route.return_value = ("chat-knowledge", "solutions")
        mock_add.return_value = {
            "entry_id": "drawer_2",
            "wing": "chat-knowledge",
            "room": "solutions",
            "collection": "chat-knowledge-solutions",
            "ingested_at": 1000.0,
            "duplicate": False,
        }

        result = inject_entry("I fixed the memory leak by closing connections")
        assert result["collection"] == "chat-knowledge-solutions"

    @patch("core.ingestion.pipeline.add_entry")
    @patch("core.ingestion.pipeline.route")
    def test_returns_entry_id(self, mock_route, mock_add):
        mock_route.return_value = ("chat-knowledge", "context")
        mock_add.return_value = {
            "entry_id": "drawer_test",
            "wing": "chat-knowledge",
            "room": "context",
            "collection": "chat-knowledge-context",
            "ingested_at": 1000.0,
            "duplicate": False,
        }

        result = inject_entry("some content")
        assert result["entry_id"] == "drawer_test"

    @patch("core.ingestion.pipeline.add_entry")
    @patch("core.ingestion.pipeline.route")
    def test_passes_metadata(self, mock_route, mock_add):
        mock_route.return_value = ("chat-knowledge", "context")
        mock_add.return_value = {
            "entry_id": "drawer_x",
            "wing": "chat-knowledge",
            "room": "context",
            "collection": "chat-knowledge-context",
            "ingested_at": 1000.0,
            "duplicate": False,
        }

        inject_entry("content", metadata={"tags": "test"})
        call_kwargs = mock_add.call_args[1]
        assert call_kwargs["wing"] == "chat-knowledge"
        assert call_kwargs["room"] == "context"

    @patch("core.ingestion.pipeline.add_entry")
    @patch("core.ingestion.pipeline.route")
    def test_wing_room_metadata_override(self, mock_route, mock_add):
        mock_route.return_value = ("code", "api")
        mock_add.return_value = {
            "entry_id": "drawer_override",
            "wing": "code",
            "room": "api",
            "collection": "code-api",
            "ingested_at": 1000.0,
            "duplicate": False,
        }

        result = inject_entry("x", metadata={"wing": "code", "room": "api"})
        assert result["collection"] == "code-api"
