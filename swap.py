#!/usr/bin/env python3
"""Swap the focused pane with its neighbour, wrapping round at the edge.

Herdr can swap from the CLI but exposes no keybinding action, so one script
backs four manifest actions and reads which one ran from
HERDR_PLUGIN_ACTION_ID.

Pressing the same direction repeatedly walks the pane that way. At the edge
herdr reports `changed: false` rather than failing, and that is the cue to send
the pane back along the row to the far end, so the row behaves as a closed
cycle instead of stopping dead.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

DIRECTIONS = ("left", "down", "up", "right")
OPPOSITE = {"left": "right", "right": "left", "up": "down", "down": "up"}
PREFIX = "swap-"
# A tab cannot hold more panes than this in practice; the bound only exists so
# a misbehaving swap can never spin forever.
MAX_STEPS = 64


def direction(action_id: str) -> str | None:
    """`swap-left` -> `left`. Anything else is not a swap."""
    if not action_id.startswith(PREFIX):
        return None
    name = action_id[len(PREFIX):]
    return name if name in DIRECTIONS else None


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr") or "herdr"


def swap_once(pane: str, where: str) -> bool:
    """One swap. True if the layout actually changed."""
    result = subprocess.run(
        [herdr_bin(), "pane", "swap", "--pane", pane, "--direction", where],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    try:
        return bool(json.loads(result.stdout)["result"]["swap"]["changed"])
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise RuntimeError(f"unreadable swap result: {error}") from None


def cycle(step, pane: str, where: str, limit: int = MAX_STEPS) -> str:
    """Swap one step, or wrap to the far end when already at the edge.

    `step(pane, direction) -> changed` is injected so the wrap can be tested
    without a session. Returns what happened, for the caller to report.
    """
    if step(pane, where):
        return "moved"

    back = OPPOSITE[where]
    moved = 0
    while moved < limit and step(pane, back):
        moved += 1
    return "wrapped" if moved else "alone"


def main() -> int:
    action_id = os.environ.get("HERDR_PLUGIN_ACTION_ID", "")
    where = direction(action_id)
    if where is None:
        print(f"unknown swap action: {action_id!r}", file=sys.stderr)
        return 1

    pane = os.environ.get("HERDR_PANE_ID", "")
    if not pane:
        raw = os.environ.get("HERDR_PLUGIN_CONTEXT_JSON")
        if raw:
            try:
                pane = json.loads(raw).get("focused_pane_id", "")
            except (json.JSONDecodeError, TypeError):
                pane = ""
    if not pane:
        pane = "--current"

    try:
        if pane == "--current":
            result = subprocess.run(
                [herdr_bin(), "pane", "current"],
                capture_output=True, text=True, timeout=10,
            )
            pane = json.loads(result.stdout)["result"]["pane"]["pane_id"]
        cycle(swap_once, pane, where)
    except (RuntimeError, OSError, subprocess.SubprocessError,
            json.JSONDecodeError, KeyError) as error:
        print(f"could not swap pane: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
