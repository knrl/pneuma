"""
Background task runner — fire-and-forget async operations that run behind
tool calls without blocking the response.

Two auto-operations:
  maybe_mine()              — incremental re-mine when files have changed
                              (fired from wake_up if a previous mine exists)
  bump_and_maybe_optimize() — incremental save counter; runs dedup+stale
                              cleanup every AUTO_OPTIMIZE_EVERY_N_SAVES saves
                              OR every AUTO_OPTIMIZE_EVERY_N_DAYS days

Both run in a thread executor (mine_project / run_refactor are synchronous)
and log to pneuma.background → ~/.pneuma/mcp-server.log.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

_log = logging.getLogger("pneuma.background")

AUTO_OPTIMIZE_EVERY_N_SAVES = 50
AUTO_OPTIMIZE_EVERY_N_DAYS = 7

# Keep strong references so GC doesn't discard running tasks
_active_tasks: set[asyncio.Task] = set()


# ── State ────────────────────────────────────────────────────────────────────

def _state_path() -> Path:
    home = Path(os.environ.get("PNEUMA_HOME", os.path.expanduser("~/.pneuma")))
    return home / "scheduler_state.json"


def _read_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    try:
        p = _state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── Task runner ──────────────────────────────────────────────────────────────

def _fire(label: str, fn, *args, **kwargs) -> None:
    """Run synchronous fn(*args, **kwargs) in a thread executor as a background task."""

    async def _run():
        _log.info("bg/%s: started", label)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
            _log.info("bg/%s: done", label)
        except Exception:
            _log.exception("bg/%s: failed", label)

    try:
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            return
        task = loop.create_task(_run())
        _active_tasks.add(task)
        task.add_done_callback(_active_tasks.discard)
    except RuntimeError:
        pass


# ── Public triggers ──────────────────────────────────────────────────────────

def maybe_mine(project_path: str) -> None:
    """
    Fire an incremental re-mine in the background if:
      1. project_path is set, AND
      2. A previous mine has run (mined_files.sqlite3 exists in the palace dir)

    Condition 2 ensures we never auto-mine on the very first run — the user
    must do that explicitly via `pneuma init` or `pneuma mine`.
    """
    if not project_path:
        return

    try:
        from core.palace import palace_path as _pp
        from core.auto_init.miner_state import resolve_state_path
        pal_dir = _pp()
    except Exception:
        return

    state_file = resolve_state_path(pal_dir)
    if not state_file or not state_file.exists():
        _log.debug("bg/mine: skipped — no prior mine state at %s", state_file)
        return

    _log.info("bg/mine: scheduling incremental re-mine for %s", project_path)

    def _do_mine():
        from core.auto_init.miner import mine_project
        mine_project(project_path, dry_run=False, incremental=True)

    _fire("mine", _do_mine)


def bump_and_maybe_optimize(n: int = 1) -> None:
    """
    Increment the persistent save counter by *n*. When the counter reaches
    AUTO_OPTIMIZE_EVERY_N_SAVES, or AUTO_OPTIMIZE_EVERY_N_DAYS days have
    passed since the last optimize, fire a background dedup+stale cleanup.
    """
    state = _read_state()
    now = time.time()

    save_count = state.get("save_count", 0) + n
    last_optimized = state.get("last_optimized", 0.0)
    days_since = (now - last_optimized) / 86_400

    due_by_count = save_count >= AUTO_OPTIMIZE_EVERY_N_SAVES
    due_by_time = days_since >= AUTO_OPTIMIZE_EVERY_N_DAYS

    if due_by_count or due_by_time:
        state["save_count"] = 0
        state["last_optimized"] = now
        _write_state(state)

        reason = "count" if due_by_count else "time"
        _log.info(
            "bg/optimize: scheduling (trigger=%s, saves=%d, days_since=%.1f)",
            reason, save_count, days_since,
        )

        def _do_optimize():
            from core.auto_org.refactor import run_optimize
            run_optimize(dry_run=False, level="standard")

        _fire("optimize", _do_optimize)
    else:
        state["save_count"] = save_count
        _write_state(state)
        _log.debug(
            "bg/optimize: not due yet (saves=%d/%d, days=%.1f/%.0f)",
            save_count, AUTO_OPTIMIZE_EVERY_N_SAVES,
            days_since, AUTO_OPTIMIZE_EVERY_N_DAYS,
        )
