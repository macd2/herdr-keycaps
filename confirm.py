#!/usr/bin/env python3
"""Ask before closing the current tab, then close it.

Herdr's `confirm_close` covers workspaces only - closing a tab never prompts,
and there is no setting for it - so the prompt lives here instead.
"""

from __future__ import annotations

import json
import os
import sys

from picker import BOLD, CHORD, DIM, RESET, WARN, api, classify, raw_mode, read_key


def current_tab() -> dict:
    """The tab the focused pane sits in, with its pane count."""
    raw = os.environ.get("HERDR_PLUGIN_CONTEXT_JSON")
    tab_id = ""
    if raw:
        try:
            tab_id = json.loads(raw).get("tab_id", "")
        except (json.JSONDecodeError, TypeError):
            tab_id = ""
    if not tab_id:
        tab_id = api("pane", "current")["pane"]["tab_id"]
    for tab in api("tab", "list")["tabs"]:
        if tab["tab_id"] == tab_id:
            return tab
    return {"tab_id": tab_id, "label": tab_id, "pane_count": 0}


def draw(tab: dict) -> None:
    panes = tab.get("pane_count", 0)
    label = tab.get("label") or tab["tab_id"]
    out = [
        "\033[H\033[2J", "",
        f"  {BOLD}CLOSE TAB{RESET}",
        "",
        f"  {label}  {DIM}({panes} pane{'s' if panes != 1 else ''}){RESET}",
        "",
        f"  {WARN}Every pane in it is killed. There is no undo.{RESET}",
        "",
        f"  {CHORD}y{RESET} close    {CHORD}n{RESET} keep",
        "",
    ]
    sys.stdout.write("\r\n".join(out) + "\r\n")
    sys.stdout.flush()


def main() -> int:
    try:
        tab = current_tab()
    except (RuntimeError, OSError, json.JSONDecodeError, KeyError) as error:
        print(f"\n  {WARN}could not read the session: {error}{RESET}\n")
        with raw_mode():
            read_key()
        return 1

    with raw_mode():
        while True:
            draw(tab)
            key = read_key()
            if key in ("y", "Y"):
                break
            # Anything else keeps the tab: only an explicit yes closes it.
            if key in ("n", "N") or classify(key) in ("cancel", "enter"):
                return 0

    try:
        api("tab", "close", tab["tab_id"])
    except (RuntimeError, OSError, json.JSONDecodeError) as error:
        sys.stdout.write(f"\r\n  {WARN}close failed: {error}{RESET}\r\n")
        sys.stdout.flush()
        with raw_mode():
            read_key()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
