"""
Tests for MCP server resilience on tool errors and disconnection.

Verifies that:
- The _safe_tool wrapper catches exceptions and returns structured errors
  instead of propagating them to the FastMCP dispatch layer
- sync and async tool functions are both handled correctly
- One tool failing does not affect other tools
- functools.wraps metadata is preserved for introspection
- All expected core tools survive the import + registration path
"""

import asyncio
from unittest.mock import patch, MagicMock

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── _safe_tool wrapper ───────────────────────────────────────────────────────

class TestSafeToolWrapper:

    def test_async_exception_returns_structured_error(self):
        """`_safe_tool` turns an async exception into a readable error string."""
        from mcp_server.server import _safe_tool

        async def bad_tool():
            raise ValueError("something went wrong")

        wrapped = _safe_tool(bad_tool)
        result = _run(wrapped())

        assert "bad_tool" in result
        assert "ValueError" in result
        assert "something went wrong" in result
        assert "still running" in result

    def test_sync_exception_returns_structured_error(self):
        """`_safe_tool` handles sync callables that raise."""
        from mcp_server.server import _safe_tool

        def bad_sync():
            raise RuntimeError("sync failure")

        wrapped = _safe_tool(bad_sync)
        result = _run(wrapped())

        assert "bad_sync" in result
        assert "RuntimeError" in result
        assert "sync failure" in result

    def test_successful_async_tool_passes_value_through(self):
        """`_safe_tool` does not alter return values from healthy tools."""
        from mcp_server.server import _safe_tool

        async def good_tool(x: int):
            return f"result={x}"

        wrapped = _safe_tool(good_tool)
        assert _run(wrapped(42)) == "result=42"

    def test_successful_sync_tool_passes_value_through(self):
        from mcp_server.server import _safe_tool

        def good_sync():
            return "sync-ok"

        wrapped = _safe_tool(good_sync)
        assert _run(wrapped()) == "sync-ok"

    def test_one_failing_tool_does_not_affect_another(self):
        """Independent wrapped tools are fully isolated."""
        from mcp_server.server import _safe_tool

        async def tool_a():
            raise KeyError("missing key")

        async def tool_b():
            return "tool_b OK"

        result_a = _run(_safe_tool(tool_a)())
        result_b = _run(_safe_tool(tool_b)())

        assert "KeyError" in result_a
        assert result_b == "tool_b OK"

    def test_functools_wraps_preserves_name(self):
        """`_safe_tool` uses `functools.wraps` so `__name__` is intact."""
        from mcp_server.server import _safe_tool

        async def my_specific_tool():
            return "ok"

        wrapped = _safe_tool(my_specific_tool)
        assert wrapped.__name__ == "my_specific_tool"

    def test_functools_wraps_preserves_docstring(self):
        from mcp_server.server import _safe_tool

        async def documented_tool():
            """This is the docstring."""
            return "ok"

        wrapped = _safe_tool(documented_tool)
        assert wrapped.__doc__ == "This is the docstring."

    def test_exception_message_references_log_location(self):
        """The error string should tell the agent where to find the full traceback."""
        from mcp_server.server import _safe_tool

        async def exploding_tool():
            raise Exception("boom")

        result = _run(_safe_tool(exploding_tool)())
        assert "mcp-server.log" in result

    def test_deeply_nested_exception_is_caught(self):
        """Exceptions raised inside nested calls are still caught."""
        from mcp_server.server import _safe_tool

        def inner():
            raise TypeError("deep error")

        async def outer():
            inner()

        result = _run(_safe_tool(outer)())
        assert "TypeError" in result
        assert "deep error" in result


# ── Server-level registration sanity ────────────────────────────────────────

class TestServerRegistration:

    def test_mcp_instance_name_is_pneuma(self):
        """The FastMCP instance must be named 'pneuma' (clients rely on this)."""
        from mcp_server.server import mcp
        assert mcp.name == "pneuma"

    def test_core_memory_tools_are_importable(self):
        """All nine memory tools must be importable without raising."""
        from mcp_server.tools.memory_tools import (
            wake_up,
            recall,
            search_memory,
            save_knowledge,
            palace_overview,
            mine_codebase,
            optimize_memory,
            delete_entry,
            initialize_project,
        )
        for fn in (wake_up, recall, search_memory, save_knowledge, palace_overview,
                   mine_codebase, optimize_memory, delete_entry, initialize_project):
            assert callable(fn)

    def test_kg_tools_are_importable(self):
        from mcp_server.tools.kg_tools import track_fact, query_facts, invalidate_fact
        for fn in (track_fact, query_facts, invalidate_fact):
            assert callable(fn)

    def test_nav_tools_are_importable(self):
        from mcp_server.tools.nav_tools import explore_palace, find_bridges
        for fn in (explore_palace, find_bridges):
            assert callable(fn)

    def test_diary_tools_are_importable(self):
        from mcp_server.tools.diary_tools import write_diary, read_diary
        for fn in (write_diary, read_diary):
            assert callable(fn)

    def test_import_tools_are_importable(self):
        from mcp_server.tools.import_tools import import_content
        assert callable(import_content)


# ── Tool resilience under simulated error conditions ────────────────────────

class TestToolResilienceUnderErrors:

    def test_wake_up_returns_error_string_when_palace_not_configured(self):
        """wake_up must not crash the server if palace isn't set up yet."""
        from mcp_server.tools.memory_tools import wake_up
        from mcp_server.server import _safe_tool

        wrapped = _safe_tool(wake_up)
        # Patch _wake_up to simulate a palace misconfiguration
        with patch("mcp_server.tools.memory_tools._wake_up", side_effect=RuntimeError("palace not configured")):
            result = _run(wrapped())

        # Should return error string, not raise
        assert isinstance(result, str)
        assert "wake_up" in result
        assert "RuntimeError" in result

    def test_search_memory_returns_error_string_on_backend_failure(self):
        from mcp_server.tools.memory_tools import search_memory
        from mcp_server.server import _safe_tool

        wrapped = _safe_tool(search_memory)
        with patch("mcp_server.tools.memory_tools._search", side_effect=ConnectionError("ChromaDB down")):
            result = _run(wrapped("some query"))

        assert isinstance(result, str)
        assert "search_memory" in result
        assert "ConnectionError" in result

    def test_save_knowledge_returns_error_string_on_backend_failure(self):
        from mcp_server.tools.memory_tools import save_knowledge
        from mcp_server.server import _safe_tool

        wrapped = _safe_tool(save_knowledge)
        with patch("mcp_server.tools.memory_tools._check_dup", side_effect=IOError("disk full")):
            result = _run(wrapped("important fact"))

        assert isinstance(result, str)
        assert "save_knowledge" in result
