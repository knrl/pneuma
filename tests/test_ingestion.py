"""Tests for core/ingestion/pipeline — inject_entry auto-routing."""

from unittest.mock import patch

import pytest

from core.ingestion.pipeline import inject_entry
from core.auto_org.router import RoutingConfig, RoutingRule


_MOCK_RESULT = {
    "entry_id": "drawer_1",
    "wing": "chat",
    "room": "decisions",
    "collection": "chat-decisions",
    "ingested_at": 1000.0,
    "duplicate": False,
}


class TestInjectEntry:
    @patch("core.palace.add_entry")
    @patch("core.ingestion.pipeline._route_full")
    def test_routes_decision_content(self, mock_route, mock_add):
        mock_route.return_value = ("chat", "decisions", "decision")
        mock_add.return_value = {**_MOCK_RESULT, "collection": "chat-decisions"}

        result = inject_entry("We decided to use PostgreSQL")
        assert result["collection"] == "chat-decisions"
        mock_add.assert_called_once()

    @patch("core.palace.add_entry")
    @patch("core.ingestion.pipeline._route_full")
    def test_routes_solution_content(self, mock_route, mock_add):
        mock_route.return_value = ("chat", "solutions", "solution")
        mock_add.return_value = {**_MOCK_RESULT, "room": "solutions", "collection": "chat-solutions"}

        result = inject_entry("I fixed the memory leak by closing connections")
        assert result["collection"] == "chat-solutions"

    @patch("core.palace.add_entry")
    @patch("core.ingestion.pipeline._route_full")
    def test_returns_entry_id(self, mock_route, mock_add):
        mock_route.return_value = ("chat", "general", None)
        mock_add.return_value = {**_MOCK_RESULT, "entry_id": "drawer_test"}

        result = inject_entry("some content")
        assert result["entry_id"] == "drawer_test"

    @patch("core.palace.add_entry")
    @patch("core.ingestion.pipeline._route_full")
    def test_passes_metadata(self, mock_route, mock_add):
        mock_route.return_value = ("chat", "general", None)
        mock_add.return_value = {**_MOCK_RESULT}

        inject_entry("content", metadata={"tags": "test"})
        call_kwargs = mock_add.call_args[1]
        assert call_kwargs["wing"] == "chat"
        assert call_kwargs["room"] == "general"

    @patch("core.palace.add_entry")
    @patch("core.ingestion.pipeline._route_full")
    def test_wing_room_metadata_override(self, mock_route, mock_add):
        mock_route.return_value = ("code", "src", None)
        mock_add.return_value = {**_MOCK_RESULT, "collection": "code-src"}

        result = inject_entry("x", metadata={"wing": "code", "room": "src"})
        assert result["collection"] == "code-src"

    @patch("core.palace.add_entry")
    def test_custom_routing_config(self, mock_add):
        mock_add.return_value = {**_MOCK_RESULT, "collection": "chat-inbox"}

        cfg = RoutingConfig(
            rules=[RoutingRule(keywords=["postmortem"], target=("chat", "inbox"))],
            default=("chat", "general"),
        )
        inject_entry("postmortem from last incident", routing_config=cfg)
        call_kwargs = mock_add.call_args[1]
        assert call_kwargs["wing"] == "chat"
        assert call_kwargs["room"] == "inbox"

    @patch("core.palace.add_entry")
    @patch("core.ingestion.pipeline._route_full")
    def test_semantic_type_in_result(self, mock_route, mock_add):
        mock_route.return_value = ("chat", "decisions", "decision")
        mock_add.return_value = {**_MOCK_RESULT}

        result = inject_entry("We decided to use PostgreSQL")
        assert result["semantic_type"] == "decision"

    @patch("core.palace.add_entry")
    @patch("core.ingestion.pipeline._route_full")
    def test_semantic_type_injected_into_metadata(self, mock_route, mock_add):
        mock_route.return_value = ("chat", "solutions", "solution")
        mock_add.return_value = {**_MOCK_RESULT, "collection": "chat-solutions"}

        inject_entry("I fixed the memory leak")
        call_kwargs = mock_add.call_args[1]
        assert call_kwargs["metadata"].get("semantic_type") == "solution"

    @patch("core.palace.add_entry")
    @patch("core.ingestion.pipeline._route_full")
    def test_general_content_has_no_semantic_type(self, mock_route, mock_add):
        mock_route.return_value = ("chat", "general", None)
        mock_add.return_value = {**_MOCK_RESULT, "collection": "chat-general"}

        result = inject_entry("some generic message")
        assert result["semantic_type"] is None

    @patch("core.palace.add_entry")
    @patch("core.ingestion.pipeline._route_full")
    def test_existing_semantic_type_not_overwritten(self, mock_route, mock_add):
        mock_route.return_value = ("chat", "decisions", "decision")
        mock_add.return_value = {**_MOCK_RESULT}

        inject_entry("We decided to use PostgreSQL", metadata={"semantic_type": "custom"})
        call_kwargs = mock_add.call_args[1]
        assert call_kwargs["metadata"].get("semantic_type") == "custom"
