#!/usr/bin/env python3
"""Pick a tab and move the focused pane into it.

Herdr has no keybinding action for moving a pane between tabs - the only
move_* actions move whole tabs - so this drives `herdr pane move` instead.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys

BOLD, CHORD, DIM, WARN, RESET = (
    "\033[1m", "\033[36m", "\033[2m", "\033[33m", "\033[0m",
)


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr") or "herdr"


def api(*args: str) -> dict:
    result = subprocess.run([herdr_bin(), *args],
                            capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return json.loads(result.stdout)["result"]


def focused_pane() -> tuple[str, str]:
    """(pane_id, tab_id) of the pane to move.

    A popup is not a tiled pane and gets no HERDR_PANE_ID, so the underlying
    pane comes from the plugin context, with the CLI as a fallback.
    """
    raw = os.environ.get("HERDR_PLUGIN_CONTEXT_JSON")
    if raw:
        try:
            ctx = json.loads(raw)
            if ctx.get("focused_pane_id"):
                return ctx["focused_pane_id"], ctx.get("tab_id", "")
        except (json.JSONDecodeError, TypeError):
            pass
    pane = api("pane", "current")["pane"]
    return pane["pane_id"], pane["tab_id"]


# Moving into an existing tab needs a placement: that tab already has panes,
# and herdr rejects --tab without --split. --new-tab takes no split.
SPLIT = "right"


def move_args(pane_id: str, choice: dict) -> list[str]:
    """argv for one move. Kept pure so it can be tested without a terminal."""
    if choice["kind"] == "new_workspace":
        return ["pane", "move", pane_id, "--new-workspace"]
    if choice["kind"] == "new_tab":
        args = ["pane", "move", pane_id, "--new-tab"]
        if choice.get("workspace_id"):
            args += ["--workspace", choice["workspace_id"]]
        return args
    return ["pane", "move", pane_id, "--tab", choice["tab_id"], "--split", SPLIT]


def destinations() -> list[tuple[dict, list[dict]]]:
    """Every workspace with its own tabs."""
    spaces = api("workspace", "list")["workspaces"]
    return [(ws, api("tab", "list", "--workspace", ws["workspace_id"])["tabs"])
            for ws in spaces]


def build_rows(spaces: list[tuple[dict, list[dict]]], current_tab: str) -> list[dict]:
    """Headings and destinations, in the order they are drawn.

    A heading names the workspace the tabs beneath it belong to and cannot be
    chosen. The tab the pane already sits in is never offered.
    """
    rows: list[dict] = []
    for workspace, tabs in spaces:
        rows.append({"kind": "heading",
                     "label": workspace.get("label") or workspace["workspace_id"]})
        for tab in tabs:
            if tab["tab_id"] == current_tab:
                continue
            rows.append({"kind": "tab", "tab_id": tab["tab_id"],
                         "label": tab.get("label") or tab["tab_id"],
                         "panes": tab.get("pane_count", 0)})
        rows.append({"kind": "new_tab", "label": "a new tab here",
                     "workspace_id": workspace["workspace_id"]})
    rows.append({"kind": "new_workspace", "label": "a new workspace"})
    return rows


def selectable(rows: list[dict]) -> list[int]:
    """Indices of rows a person can actually choose."""
    return [i for i, row in enumerate(rows) if row["kind"] != "heading"]


# Esc alone cancels, but arrows arrive as Esc [ A. They are told apart by
# whether more bytes follow immediately, not by guessing.
ESC_TIMEOUT = 0.05


def classify(seq: str) -> str:
    """Map a key sequence to an intent. Pure, so it can be tested directly."""
    if seq in ("\x1b[A", "\x1bOA", "k"):
        return "up"
    if seq in ("\x1b[B", "\x1bOB", "j"):
        return "down"
    if seq in ("\r", "\n", " "):
        return "enter"
    if seq in ("q", "\x1b", "\x03"):
        return "cancel"
    if len(seq) == 1 and seq.isdigit():
        return seq
    return ""


@contextlib.contextmanager
def raw_mode():
    """Raw for the whole session, not per keypress.

    Toggling it around each read leaves the tty canonical between frames, and
    anything typed in that window is line-buffered: an escape sequence arrives
    mangled and an arrow reads as a bare Esc.
    """
    import termios
    import tty

    fd = sys.stdin.fileno()
    try:
        saved = termios.tcgetattr(fd)
    except termios.error:        # not a terminal, e.g. piped
        yield
        return
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def read_key() -> str:
    """One key from the terminal, escape sequences included."""
    import select

    fd = sys.stdin.fileno()
    # os.read, not sys.stdin.read: the latter buffers the whole sequence out of
    # reach, so select() reports nothing pending and an arrow looks like a bare
    # Esc.
    seq = os.read(fd, 1).decode("utf-8", "replace")
    if seq == "\x1b":
        # Only a real escape sequence has bytes waiting right behind it.
        while select.select([fd], [], [], ESC_TIMEOUT)[0]:
            char = os.read(fd, 1).decode("utf-8", "replace")
            seq += char
            if char.isalpha() or char == "~":
                break
    return seq


def draw(rows: list[dict], picks: list[int], cursor: int) -> None:
    out = ["\033[H\033[2J"]  # home, clear: the list redraws in place
    out.append("")
    out.append(f"  {BOLD}MOVE PANE{RESET}  {DIM}pick a destination{RESET}")
    out.append("")
    number = 0
    for index, row in enumerate(rows):
        if row["kind"] == "heading":
            out.append("")
            out.append(f"  {BOLD}{row['label']}{RESET}")
            continue
        number += 1
        if row["kind"] == "tab":
            panes = row["panes"]
            text = f"{row['label']}  {DIM}({panes} pane{'s' if panes != 1 else ''}){RESET}"
        else:
            text = f"{DIM}{row['label']}{RESET}"
        chosen = index == picks[cursor]
        marker = f"{CHORD}\u203a{RESET}" if chosen else " "
        out.append(f"  {marker} {CHORD}{number}{RESET}  "
                   f"{BOLD + text + RESET if chosen else text}")
    out.append("")
    out.append(f"  {DIM}\u2191\u2193 or number \u00b7 enter to move \u00b7 q to cancel{RESET}")
    sys.stdout.write("\r\n".join(out) + "\r\n")
    sys.stdout.flush()


def main() -> int:
    try:
        pane_id, current_tab = focused_pane()
        rows = build_rows(destinations(), current_tab)
    except (RuntimeError, OSError, json.JSONDecodeError, KeyError) as error:
        print(f"\n  {WARN}could not read the session: {error}{RESET}\n")
        with raw_mode():
            read_key()
        return 1

    picks = selectable(rows)
    cursor = 0

    with raw_mode():
        while True:
            draw(rows, picks, cursor)
            intent = classify(read_key())
            if intent == "cancel":
                return 0
            if intent == "up":
                cursor = (cursor - 1) % len(picks)
                continue
            if intent == "down":
                cursor = (cursor + 1) % len(picks)
                continue
            if intent.isdigit() and 1 <= int(intent) <= len(picks):
                cursor = int(intent) - 1
            elif intent != "enter":
                continue
            break

    try:
        api(*move_args(pane_id, rows[picks[cursor]]))
    except (RuntimeError, OSError, json.JSONDecodeError) as error:
        sys.stdout.write(f"\r\n  {WARN}move failed: {error}{RESET}\r\n")
        sys.stdout.flush()
        with raw_mode():
            read_key()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
