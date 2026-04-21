"""Tests for chat_bot/preprocessing/noise_filter — embedding similarity classifier."""

import pytest

from chat_bot.preprocessing.noise_filter import (
    BufferedMessage,
    filter_messages,
    _rule_verdict,
)


def _msg(text: str) -> BufferedMessage:
    return BufferedMessage(user="U1", text=text, channel="C1", ts="1.0")


# ── Structural fast-path: always drop ────────────────────────────

class TestStructuralDrop:
    def test_empty_message(self):
        assert _rule_verdict("") == "drop"
        assert _rule_verdict("   ") == "drop"

    def test_short_noise(self):
        # Short messages with no structural keep-signal are dropped before
        # the model is consulted.
        assert _rule_verdict("lol") == "drop"
        assert _rule_verdict("haha") == "drop"
        assert _rule_verdict("😂🤣") == "drop"
        assert _rule_verdict("brb") == "drop"
        assert _rule_verdict("good morning") == "drop"
        assert _rule_verdict("Good Morning everyone") == "drop"
        assert _rule_verdict("happy friday") == "drop"
        assert _rule_verdict("Happy Weekend!") == "drop"
        assert _rule_verdict("hey!") == "drop"
        assert _rule_verdict("hi") == "drop"
        assert _rule_verdict("hello") == "drop"
        assert _rule_verdict("ok sure") == "drop"
        assert _rule_verdict("let's grab lunch together") == "drop"

    def test_karma_bots(self):
        assert _rule_verdict("<@U123> ++") == "drop"


# ── Structural fast-path: always keep ────────────────────────────

class TestStructuralKeep:
    def test_code_fences(self):
        assert _rule_verdict("Try this:\n```\nprint('hello')\n```") == "keep"

    def test_question_mark(self):
        # Any message containing '?' is treated as a question and kept
        # regardless of length or language.
        assert _rule_verdict("why does this test fail?") == "keep"
        assert _rule_verdict("how do I configure the database connection?") == "keep"
        assert _rule_verdict("how do I fix the flaky test?") == "keep"


# ── Embedding similarity (longer messages, no structural signal) ──

class TestEmbeddingSimilarity:
    def test_technical_messages_kept(self):
        assert _rule_verdict("There's a bug in the payment module") == "keep"
        assert _rule_verdict("Getting an error: NullPointerException") == "keep"
        assert _rule_verdict("We need to deploy the fix to staging") == "keep"
        assert _rule_verdict("We decided to switch to PostgreSQL") == "keep"
        assert _rule_verdict("Found a workaround for the timeout issue") == "keep"

    def test_social_noise_dropped(self):
        assert _rule_verdict("want to order some pizza and grab coffee") == "drop"

    def test_ambiguous_long_message_kept(self):
        # Ambiguous messages (low similarity to both groups) default to keep.
        text = "I was thinking about that thing we discussed yesterday in the meeting"
        assert _rule_verdict(text) == "keep"


# ── filter_messages integration ──────────────────────────────────

class TestFilterMessages:
    def test_filters_noise_keeps_signal(self):
        messages = [
            _msg("good morning"),
            _msg("There's a bug in the auth module"),
            _msg("lol"),
            _msg("how do I fix the flaky test?"),
            _msg("hi!"),
        ]
        kept = filter_messages(messages)
        texts = [m.text for m in kept]
        assert "There's a bug in the auth module" in texts
        assert "how do I fix the flaky test?" in texts
        assert "good morning" not in texts
        assert "lol" not in texts
        assert "hi!" not in texts

    def test_empty_input(self):
        assert filter_messages([]) == []
