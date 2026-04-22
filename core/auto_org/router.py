"""
Content router — classifies incoming content and returns
the target (wing, room) pair for storage in the MemPalace.

Priority order:
  1. Explicit wing/room in metadata — always honoured.
  2. User-defined rules from .pneuma.yaml (routing.rules).
  3. Built-in keyword rules.
  4. Default fallback (routing.default, or ("chat", "general")).

User rules REPLACE the built-in rules entirely when specified.
The default fallback can be overridden independently via routing.default.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class RoutingRule:
    keywords: list[str]
    target: tuple[str, str]


@dataclass
class RoutingConfig:
    rules: list[RoutingRule] = field(default_factory=list)
    default: tuple[str, str] = ("chat", "general")


# ── Built-in defaults ────────────────────────────────────────────────────────

_BUILTIN_RULES: list[RoutingRule] = [
    RoutingRule(
        keywords=["escalate", "help needed", "blocked", "stuck", "can't figure"],
        target=("chat", "escalations"),
    ),
    RoutingRule(
        keywords=["decided", "decision", "we agreed", "we chose", "convention", "standard", "architecture"],
        target=("chat", "decisions"),
    ),
    RoutingRule(
        keywords=["style guide", "naming convention", "lint", "format"],
        target=("chat", "conventions"),
    ),
    RoutingRule(
        keywords=["workaround", "hack", "temp fix", "temporary", "hotfix"],
        target=("chat", "workarounds"),
    ),
    RoutingRule(
        keywords=["solution", "solved", "fixed", "answer", "resolved"],
        target=("chat", "solutions"),
    ),
]

_DEFAULT_FALLBACK: tuple[str, str] = ("chat", "general")


def default_config() -> RoutingConfig:
    """Return a RoutingConfig populated with the built-in rules and default fallback."""
    return RoutingConfig(rules=list(_BUILTIN_RULES), default=_DEFAULT_FALLBACK)


# ── Config loading ────────────────────────────────────────────────────────────

def load_routing_config(project_path: str) -> RoutingConfig:
    """
    Load routing config from .pneuma.yaml at project_path.

    Reads the top-level ``routing:`` section:

      routing:
        rules:
          - keywords: ["decided", "decision", "we chose"]
            target: [chat, decisions]
          - keywords: ["workaround", "hack"]
            target: [chat, workarounds]
        default: [chat, general]

    If ``rules`` is present it REPLACES the built-in rules entirely.
    If ``default`` is present it overrides the fallback wing/room.
    If the section is absent entirely, built-in defaults are used.
    """
    raw = _read_yaml_section(project_path)
    if raw is None:
        return default_config()

    cfg = default_config()

    rules_raw = raw.get("rules")
    if isinstance(rules_raw, list):
        parsed: list[RoutingRule] = []
        for item in rules_raw:
            if not isinstance(item, dict):
                continue
            kws = item.get("keywords")
            tgt = item.get("target")
            if isinstance(kws, list) and isinstance(tgt, (list, tuple)) and len(tgt) == 2:
                parsed.append(RoutingRule(
                    keywords=[str(k) for k in kws],
                    target=(str(tgt[0]), str(tgt[1])),
                ))
        if parsed:
            cfg.rules = parsed  # user rules replace built-ins

    default_raw = raw.get("default")
    if isinstance(default_raw, (list, tuple)) and len(default_raw) == 2:
        cfg.default = (str(default_raw[0]), str(default_raw[1]))

    return cfg


def _read_yaml_section(project_path: str) -> dict | None:
    """Return the routing: section dict from .pneuma.yaml, or None."""
    from pathlib import Path
    root = Path(project_path)
    for name in (".pneuma.yaml", ".pneuma.yml"):
        path = root / name
        if not path.exists():
            continue
        try:
            import yaml  # type: ignore
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                section = data.get("routing")
                return section if isinstance(section, dict) else None
        except Exception:
            return None
    path = root / ".pneuma.json"
    if path.exists():
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                section = data.get("routing")
                return section if isinstance(section, dict) else None
        except Exception:
            pass
    return None


# ── Routing ───────────────────────────────────────────────────────────────────

def route(
    content: str,
    metadata: dict | None = None,
    config: RoutingConfig | None = None,
) -> tuple[str, str]:
    """
    Return the best ``(wing, room)`` pair for *content*.

    1. If metadata already contains ``wing`` and ``room``, honour them.
    2. Try rules from *config* (user-defined or built-in).
    3. Fall back to config.default.
    """
    if metadata and metadata.get("wing") and metadata.get("room"):
        return (metadata["wing"], metadata["room"])

    cfg = config or default_config()

    text = content.lower()
    for rule in cfg.rules:
        if any(kw in text for kw in rule.keywords):
            return rule.target

    return cfg.default


# ── Kept for tests that import this directly ──────────────────────────────────

def _keyword_match(content: str) -> tuple[str, str] | None:
    """Match against built-in rules only. Used by unit tests."""
    text = content.lower()
    for rule in _BUILTIN_RULES:
        if any(kw in text for kw in rule.keywords):
            return rule.target
    return None
