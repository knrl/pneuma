"""Tests for core/auto_org — content routing and duplicate detection."""

import tempfile

import pytest

from core.auto_org.router import route, _keyword_match


# ── Router ───────────────────────────────────────────────────────

class TestRoute:
    def test_metadata_wing_room_override(self):
        result = route("anything", {"wing": "custom", "room": "override"})
        assert result == ("custom", "override")

    def test_escalation_keywords(self):
        assert route("I'm stuck on this issue") == ("chat", "escalations")
        assert route("help needed with auth") == ("chat", "escalations")

    def test_decision_keywords(self):
        assert route("We decided to use PostgreSQL") == ("chat", "decisions")
        assert route("We agreed on REST for the API") == ("chat", "decisions")

    def test_convention_keywords(self):
        assert route("See the style guide for naming") == ("chat", "conventions")

    def test_workaround_keywords(self):
        assert route("I used a workaround for the timeout") == ("chat", "workarounds")
        assert route("Applied a hotfix for the crash") == ("chat", "workarounds")

    def test_solution_keywords(self):
        assert route("I solved the memory leak") == ("chat", "solutions")
        assert route("The bug is fixed now") == ("chat", "solutions")

    def test_code_content_falls_through_to_default(self):
        # Code-wing routing was removed — code content is now routed by
        # the miner via directory structure, not the keyword router.
        assert route("The API endpoint returns 500") == ("chat", "context")
        assert route("Updated the database schema migration") == ("chat", "context")
        assert route("Changed the config settings") == ("chat", "context")
        assert route("class UserService:") == ("chat", "context")
        assert route("def process_payment():") == ("chat", "context")

    def test_default_fallback(self):
        # No keywords → default wing/room
        result = route("Some generic long enough message that doesn't match any patterns at all whatsoever")
        assert result == ("chat", "context")

    def test_first_matching_rule_wins(self):
        # "stuck" matches escalations before anything else
        result = route("I'm stuck, need a workaround")
        assert result == ("chat", "escalations")


# ── Keyword match ────────────────────────────────────────────────

class TestKeywordMatch:
    def test_returns_none_for_no_match(self):
        assert _keyword_match("xyzzy gibberish") is None

    def test_case_insensitive(self):
        assert _keyword_match("We DECIDED to use Go") == ("chat", "decisions")
