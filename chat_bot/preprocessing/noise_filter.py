"""
Noise filter — removes non-technical chatter from raw Slack messages
before they enter the extraction pipeline.

Uses embedding similarity against a small set of labelled seed examples
via the already-installed ONNX runtime and ChromaDB's bundled
all-MiniLM-L6-v2 model.  No additional dependencies are required.

Falls back to a length heuristic if the model is unavailable (e.g. first
run before ChromaDB has downloaded it, or import failure).
"""

import re
from dataclasses import dataclass
from typing import Optional

import numpy as np

# ── Structural fast-path checks (language-agnostic, no model needed) ─────────

# Karma-bot commands are structural noise.
_KARMA_BOT_RE = re.compile(r"^<@\w+>\s*(\+\+|--)\s*$")
# Fenced code blocks are always signal.
_CODE_FENCE_RE = re.compile(r"```|~~~")

# Messages shorter than this, with no structural keep-signal, are dropped
# before the model is consulted.
_MIN_USEFUL_LENGTH = 30

# ── Seed examples for embedding similarity ────────────────────────────────────

_NOISE_SEEDS: list[str] = [
    "good morning everyone!",
    "lol that's hilarious",
    "brb back in 5",
    "sounds good 👍",
    "happy friday team!",
    "anyone up for coffee?",
    "see you all tomorrow",
    "ok thanks for the update",
    "haha yeah totally",
    "let's grab lunch today",
    "afk for a bit",
    "noted, will do",
]

_USEFUL_SEEDS: list[str] = [
    "bug: connection timeout in production",
    "there's a bug in the login flow",
    "error: NullPointerException at line 42",
    "workaround: set MAX_RETRIES=3 in env",
    "we decided to use JWT for auth",
    "deploy failed, rolling back to v1.2",
    "how do I fix the flaky test?",
    "stack trace shows NPE in handler",
    "PR merged, closes issue 123",
    "hotfix pushed to prod branch",
    "the auth token expires after 5 min",
    "set the env var to disable caching",
    "repro steps: start server then hit endpoint",
    "discussed the approach we should take going forward",
]


@dataclass
class BufferedMessage:
    """A single buffered Slack message ready for filtering."""
    user: str
    text: str
    channel: str
    ts: str
    thread_ts: str | None = None


def filter_messages(
    messages: list[BufferedMessage],
) -> list[BufferedMessage]:
    """
    Filter messages using embedding similarity against seed examples.
    Returns only messages likely to contain useful content.
    """
    return [msg for msg in messages if _is_useful(msg.text)]


# ── Internal helpers ─────────────────────────────────────────────

def _is_useful(text: str) -> bool:
    """Quick yes/no: is this message worth keeping?"""
    return _rule_verdict(text) != "drop"


def _rule_verdict(text: str) -> str:
    """Return 'keep' or 'drop'."""
    stripped = text.strip()

    # Empty / whitespace
    if not stripped:
        return "drop"

    # Structural: karma-bot commands are always noise
    if _KARMA_BOT_RE.match(stripped):
        return "drop"

    # Structural: fenced code blocks are always signal
    if _CODE_FENCE_RE.search(stripped):
        return "keep"

    # Structural: any question mark indicates a question — keep
    if "?" in stripped:
        return "keep"

    # Short messages with no structural keep-signal are almost always noise
    if len(stripped) < _MIN_USEFUL_LENGTH:
        return "drop"

    # Embedding similarity for longer, ambiguous messages
    if _ensure_model():
        return _embedding_verdict(stripped)

    # Fallback when model is unavailable: keep long messages to avoid
    # dropping legitimate knowledge.
    return "keep"


# ── Lazy model initialisation ─────────────────────────────────────

_embedder = None
_noise_matrix: Optional[np.ndarray] = None
_useful_matrix: Optional[np.ndarray] = None
_model_failed: bool = False


def _ensure_model() -> bool:
    """
    Load the ONNX embedder and pre-compute seed matrices on first call.
    Returns True if the model is ready, False if loading failed.
    """
    global _embedder, _noise_matrix, _useful_matrix, _model_failed

    if _model_failed:
        return False
    if _noise_matrix is not None:
        return True

    try:
        from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import (
            ONNXMiniLM_L6_V2,
        )
        _embedder = ONNXMiniLM_L6_V2()
        # Embed all seeds once and store as (N, 384) float32 matrices.
        # ONNXMiniLM_L6_V2 returns L2-normalised vectors, so cosine
        # similarity reduces to a plain dot product.
        _noise_matrix = np.array(_embedder(_NOISE_SEEDS), dtype=np.float32)
        _useful_matrix = np.array(_embedder(_USEFUL_SEEDS), dtype=np.float32)
        return True
    except Exception:
        _model_failed = True
        return False


def _embedding_verdict(text: str) -> str:
    """Classify *text* by cosine similarity to noise / useful seed matrices."""
    vec = np.array(_embedder([text])[0], dtype=np.float32)
    noise_score = float(np.max(vec @ _noise_matrix.T))
    useful_score = float(np.max(vec @ _useful_matrix.T))
    # Ties go to keep — better to retain slightly noisy input than lose knowledge.
    return "drop" if noise_score > useful_score else "keep"
