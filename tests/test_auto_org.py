"""Tests for core/auto_org — content routing and duplicate detection."""

import json
import tempfile
from pathlib import Path

import pytest

from core.auto_org.router import (
    route,
    classify,
    _keyword_match,
    RoutingConfig,
    RoutingRule,
    load_routing_config,
    default_config,
)


# ── Built-in routing (no config) ─────────────────────────────────

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
        # Code-wing routing was removed — code content is routed by
        # the miner via directory structure, not the keyword router.
        assert route("The API endpoint returns 500") == ("chat", "general")
        assert route("Updated the database schema migration") == ("chat", "general")
        assert route("Changed the config settings") == ("chat", "general")
        assert route("class UserService:") == ("chat", "general")
        assert route("def process_payment():") == ("chat", "general")

    def test_default_fallback(self):
        result = route("Some generic message that doesn't match any patterns at all")
        assert result == ("chat", "general")

    def test_first_matching_rule_wins(self):
        # "stuck" matches escalations; "workaround" would match workarounds
        # but escalations rule comes first in built-ins
        result = route("I'm stuck, need a workaround")
        assert result == ("chat", "escalations")


# ── Keyword match ─────────────────────────────────────────────────

class TestKeywordMatch:
    def test_returns_none_for_no_match(self):
        assert _keyword_match("xyzzy gibberish") is None

    def test_case_insensitive(self):
        assert _keyword_match("We DECIDED to use Go") == ("chat", "decisions")


# ── RoutingConfig dataclass ───────────────────────────────────────

class TestRoutingConfig:
    def test_default_config_has_builtin_rules(self):
        cfg = default_config()
        assert len(cfg.rules) > 0
        assert cfg.default == ("chat", "general")

    def test_custom_config_overrides_rules(self):
        cfg = RoutingConfig(
            rules=[RoutingRule(keywords=["rfc", "proposal"], target=("chat", "decisions"))],
            default=("chat", "general"),
        )
        assert route("This is an RFC for the new auth flow", config=cfg) == ("chat", "decisions")

    def test_custom_config_default_override(self):
        cfg = RoutingConfig(rules=[], default=("chat", "inbox"))
        assert route("some unmatched content xyz", config=cfg) == ("chat", "inbox")

    def test_user_rules_replace_builtins(self):
        # With a custom config that has no decision rule,
        # "decided" should fall through to default.
        cfg = RoutingConfig(
            rules=[RoutingRule(keywords=["hotfix"], target=("chat", "workarounds"))],
            default=("chat", "general"),
        )
        assert route("We decided to use Postgres", config=cfg) == ("chat", "general")
        assert route("applied a hotfix today", config=cfg) == ("chat", "workarounds")

    def test_metadata_override_still_wins_with_custom_config(self):
        cfg = RoutingConfig(rules=[], default=("chat", "general"))
        result = route("anything", {"wing": "code", "room": "src"}, config=cfg)
        assert result == ("code", "src")


# ── load_routing_config ───────────────────────────────────────────

class TestLoadRoutingConfig:
    def test_returns_defaults_when_no_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_routing_config(tmp)
            assert cfg.default == ("chat", "general")
            assert len(cfg.rules) > 0  # built-in rules

    def test_loads_rules_from_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".pneuma.yaml").write_text(
                "routing:\n"
                "  rules:\n"
                "    - keywords: [rfc, proposal]\n"
                "      target: [chat, decisions]\n"
                "    - keywords: [postmortem]\n"
                "      target: [chat, solutions]\n"
                "  default: [chat, inbox]\n",
                encoding="utf-8",
            )
            cfg = load_routing_config(tmp)
            assert cfg.default == ("chat", "inbox")
            assert len(cfg.rules) == 2
            assert cfg.rules[0].target == ("chat", "decisions")
            assert cfg.rules[1].target == ("chat", "solutions")
            assert "rfc" in cfg.rules[0].keywords

    def test_loads_default_override_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".pneuma.yaml").write_text(
                "routing:\n"
                "  default: [chat, inbox]\n",
                encoding="utf-8",
            )
            cfg = load_routing_config(tmp)
            # default overridden; rules fall back to built-ins
            assert cfg.default == ("chat", "inbox")
            assert len(cfg.rules) > 0

    def test_loads_from_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "routing": {
                    "rules": [
                        {"keywords": ["postmortem"], "target": ["chat", "solutions"]}
                    ],
                    "default": ["chat", "general"],
                }
            }
            Path(tmp, ".pneuma.json").write_text(json.dumps(config), encoding="utf-8")
            cfg = load_routing_config(tmp)
            assert cfg.rules[0].target == ("chat", "solutions")

    def test_ignores_malformed_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".pneuma.yaml").write_text(
                "routing:\n"
                "  rules:\n"
                "    - keywords: [good]\n"
                "      target: [chat, decisions]\n"
                "    - not_a_dict: true\n"
                "    - keywords: [missing_target]\n"
                "  default: [chat, general]\n",
                encoding="utf-8",
            )
            cfg = load_routing_config(tmp)
            # Only the valid rule should be parsed
            assert len(cfg.rules) == 1
            assert "good" in cfg.rules[0].keywords

    def test_returns_defaults_when_routing_section_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".pneuma.yaml").write_text(
                "miner:\n  chunk_size: 2000\n",
                encoding="utf-8",
            )
            cfg = load_routing_config(tmp)
            assert cfg.default == ("chat", "general")
            assert len(cfg.rules) > 0

    def test_loads_semantic_type_from_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".pneuma.yaml").write_text(
                "routing:\n"
                "  rules:\n"
                "    - keywords: [rfc]\n"
                "      target: [chat, decisions]\n"
                "      semantic_type: decision\n"
                "    - keywords: [postmortem]\n"
                "      target: [chat, solutions]\n"
                "  default: [chat, general]\n",
                encoding="utf-8",
            )
            cfg = load_routing_config(tmp)
            assert cfg.rules[0].semantic_type == "decision"
            assert cfg.rules[1].semantic_type is None


# ── classify() ───────────────────────────────────────────────────────────────

class TestClassify:
    def test_decision_content(self):
        assert classify("We decided to use PostgreSQL") == "decision"

    def test_solution_content(self):
        assert classify("I fixed the memory leak") == "solution"

    def test_workaround_content(self):
        assert classify("Applied a hotfix for the crash") == "workaround"

    def test_escalation_content(self):
        assert classify("I'm stuck on this issue") == "escalation"

    def test_convention_content(self):
        assert classify("See the style guide for naming") == "convention"

    def test_general_content_returns_none(self):
        assert classify("some random message") is None

    def test_explicit_metadata_passthrough(self):
        # When wing/room are explicit, semantic_type comes from metadata if set
        result = classify("anything", {"wing": "chat", "room": "decisions", "semantic_type": "decision"})
        assert result == "decision"

    def test_explicit_metadata_no_semantic_type(self):
        # Explicit routing without semantic_type → None
        result = classify("anything", {"wing": "chat", "room": "decisions"})
        assert result is None

    def test_custom_config_semantic_type(self):
        cfg = RoutingConfig(
            rules=[RoutingRule(keywords=["postmortem"], target=("chat", "solutions"), semantic_type="solution")],
            default=("chat", "general"),
        )
        assert classify("postmortem from last incident", config=cfg) == "solution"

    def test_builtin_rules_have_semantic_types(self):
        cfg = default_config()
        types = {r.semantic_type for r in cfg.rules if r.semantic_type}
        assert types == {"escalation", "decision", "convention", "workaround", "solution"}


# ── RoutingRule.semantic_type ─────────────────────────────────────────────────

class TestRoutingRuleSemanticType:
    def test_default_is_none(self):
        rule = RoutingRule(keywords=["foo"], target=("chat", "general"))
        assert rule.semantic_type is None

    def test_explicit_semantic_type(self):
        rule = RoutingRule(keywords=["foo"], target=("chat", "decisions"), semantic_type="decision")
        assert rule.semantic_type == "decision"
