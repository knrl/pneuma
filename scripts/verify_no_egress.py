"""
verify_no_egress.py — confirm zero outbound network calls during retrieval.

Monkey-patches socket.connect to intercept any outbound connection attempt
made while running a retrieval cycle. Fails with a non-zero exit code if
any unexpected network call is detected.

Usage:
    python scripts/verify_no_egress.py
"""

import socket
import sys
import os

# Allow connections only to localhost (ChromaDB, SQLite via MemPalace).
_ALLOWED_HOSTS = {"127.0.0.1", "::1", "localhost"}

_original_connect = socket.socket.connect


def _guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else str(address)
    if host not in _ALLOWED_HOSTS:
        raise AssertionError(
            f"EGRESS DETECTED: outbound connection to {address!r} "
            "during retrieval — this should never happen."
        )
    return _original_connect(self, address)


def run_retrieval():
    """Run a retrieval cycle against the configured palace."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from dotenv import load_dotenv
    load_dotenv()

    from core.palace import init_palace
    from core.rag.retriever import search_memory

    init_palace()
    results = search_memory("test query for egress verification", top_k=3)
    return results


def main():
    print("Patching socket.connect to intercept outbound calls...")
    socket.socket.connect = _guarded_connect

    try:
        results = run_retrieval()
        print(f"Retrieval completed — {len(results)} result(s) returned.")
        print("PASS: zero outbound network calls detected during retrieval.")
        sys.exit(0)
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: retrieval raised an unexpected exception: {e}", file=sys.stderr)
        sys.exit(2)
    finally:
        socket.socket.connect = _original_connect


if __name__ == "__main__":
    main()
