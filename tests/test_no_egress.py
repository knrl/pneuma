"""
Tests that zero outbound network calls are made during retrieval.

Monkey-patches socket.connect to intercept any connection attempt that
targets a non-localhost host while a retrieval cycle runs.

Covers checklist item:
  [x] Run verify_no_egress.py — confirm zero outbound calls during retrieval
"""

import socket
import pytest

_ALLOWED_HOSTS = {"127.0.0.1", "::1", "localhost"}
_original_connect = socket.socket.connect
_egress_calls: list[tuple] = []


def _guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else str(address)
    if host not in _ALLOWED_HOSTS:
        _egress_calls.append(address)
        raise AssertionError(
            f"EGRESS DETECTED: outbound connection to {address!r} "
            "during retrieval — this should never happen."
        )
    return _original_connect(self, address)


@pytest.fixture(autouse=False)
def block_egress():
    """Patch socket.connect for the duration of a test."""
    _egress_calls.clear()
    socket.socket.connect = _guarded_connect
    yield
    socket.socket.connect = _original_connect


class TestNoEgressDuringRetrieval:

    def test_search_makes_no_outbound_calls(self, tmp_palace, block_egress):
        """semantic search must not open any external network connection."""
        from core.rag.retriever import search_memory
        results = search_memory("authentication token expiry", top_k=5)
        assert isinstance(results, list)
        assert _egress_calls == [], (
            f"Unexpected outbound calls during search: {_egress_calls}"
        )

    def test_save_and_retrieve_makes_no_outbound_calls(self, tmp_palace, block_egress):
        """Storing an entry and retrieving it must stay fully local."""
        from core.palace import add_entry, search
        add_entry(
            content="We use Redis for session caching.",
            wing="decisions", room="architecture", metadata={},
        )
        results = search("session caching", top_k=3)
        assert isinstance(results, list)
        assert _egress_calls == [], (
            f"Unexpected outbound calls during save+retrieve: {_egress_calls}"
        )

    def test_wake_up_makes_no_outbound_calls(self, tmp_palace, block_egress):
        """`wake_up` loads identity context without any network call."""
        from core.palace import wake_up
        result = wake_up(wing=None)
        assert isinstance(result, str)
        assert _egress_calls == [], (
            f"Unexpected outbound calls during wake_up: {_egress_calls}"
        )
