#!/usr/bin/env python3
"""Render every herdr keybinding currently in effect.

Herdr has no CLI that dumps resolved keybindings, so the action list and its
defaults come from `herdr --default-config`, where every action appears as a
commented `# action = "binding"` line. The user's config.toml overrides those.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

# The key plumbing every popup here shares: raw mode held for the whole
# session, one key per read, and a bare Escape told apart from an arrow by
# whether more bytes follow it. confirm.py takes the same three.
from picker import classify, raw_mode, read_key

# A commented default such as `# focus_pane_left = "prefix+h"`. Prose in that
# file can also read like an assignment, so the value is validated separately.
DEFAULT_LINE = re.compile(r"^#\s*([a-z_]+)\s*=\s*(.+)$")
SECTION_LINE = re.compile(r"^#?\s*(\[+[^\]]+\]+)")


def config_path() -> Path:
    override = os.environ.get("HERDR_CONFIG_PATH")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "herdr" / "config.toml"


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr") or "herdr"


def default_bindings() -> list[tuple[str, list[str]]]:
    """Action order and default chords, read from `herdr --default-config`."""
    try:
        raw = subprocess.run(
            [herdr_bin(), "--default-config"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []

    found: list[tuple[str, list[str]]] = []
    in_keys = False
    for line in raw.splitlines():
        section = SECTION_LINE.match(line)
        if section:
            # [[keys.command]] is a custom command, not an action.
            in_keys = section.group(1) == "[keys]"
            continue
        if not in_keys:
            continue
        match = DEFAULT_LINE.match(line.strip())
        if not match:
            continue
        action, value = match.group(1), match.group(2)
        # Only a bare string or an array of them is a binding; `# type = "popup"
        # opens a session-modal terminal` is prose.
        try:
            parsed = tomllib.loads(f"v = {strip_trailing_comment(value)}")["v"]
        except (tomllib.TOMLDecodeError, KeyError):
            continue
        chords = as_chords(parsed)
        if chords is None:
            continue
        found.append((action, chords))
    return found


def strip_trailing_comment(value: str) -> str:
    """Drop an unquoted trailing `# ...` so the remainder parses as TOML."""
    quote = ""
    for index, char in enumerate(value):
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "#":
            return value[:index].strip()
    return value.strip()


def as_chords(value: object) -> list[str] | None:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return [item for item in value if item]
    return None


def user_config(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        # No config at all means herdr runs on its own built-in defaults.
        return {}


# Groups in the order someone reaching for the cheatsheet needs them, and
# within each group the action used most often during normal work first.
# Directional sets always read up, down, right, left.
# Herdr's own config order is not useful here: it opens with help, settings and
# detach, which pushes pane and tab movement past the end of a screen.
GROUPS: list[tuple[str, list[str]]] = [
    ("Panes", [
        "focus_pane_up", "focus_pane_down", "focus_pane_right", "focus_pane_left",
        "cycle_pane_next", "cycle_pane_previous", "last_pane",
        "split_vertical", "split_horizontal", "zoom", "close_pane",
        "resize_mode", "resize_pane_up", "resize_pane_down",
        "resize_pane_right", "resize_pane_left",
        "rename_pane", "edit_scrollback", "clear_pane",
    ]),
    ("Tabs", [
        "switch_tab", "next_tab", "previous_tab", "new_tab",
        "close_tab", "rename_tab", "move_tab_next", "move_tab_previous",
    ]),
    ("Workspaces", [
        "workspace_picker", "goto", "previous_workspace", "next_workspace",
        "switch_workspace", "new_workspace", "rename_workspace", "close_workspace",
        "new_worktree", "open_worktree", "remove_worktree",
    ]),
    ("Agents", ["focus_agent", "next_agent", "previous_agent"]),
    ("Session", [
        "help", "settings", "toggle_sidebar", "copy_mode", "reload_config",
        "open_notification_target", "remote_image_paste", "detach",
    ]),
]


# Navigate mode's keys only work inside the workspace navigator and duplicate
# bindings that are reachable globally, so they are noise in a list opened to
# find something fast. group_for still names the section, for the tests and for
# anyone who wants it back.
HIDDEN_SECTIONS = {"Navigate mode"}

# Actions never listed, named one by one. Resize mode is superseded by the
# direct resize chords, and edit scrollback is undocumented by herdr and
# unused here - a row you always skip is a row in the way.
HIDDEN_ACTIONS = {"resize_mode", "edit_scrollback"}

# Built-in actions shown with your own commands rather than in their herdr
# group - reached constantly and by one key, not looked up - mapped to where
# they sit in that list. Your [[keys.command]] entries keep their config order
# around them.
PROMOTED = {"goto": 2}

# The reverse: your own commands that belong in a herdr group rather than with
# the rest, keyed by what the binding invokes. They are listed at the end of
# that group.
COMMAND_SECTIONS = {
    "macd2.keycaps.even": "Panes",
    "macd2.keycaps.swap-up": "Panes",
    "macd2.keycaps.swap-down": "Panes",
    "macd2.keycaps.swap-right": "Panes",
    "macd2.keycaps.swap-left": "Panes",
}


def command_section(entry: dict) -> str | None:
    """Which group a [[keys.command]] belongs to, or None for COMMANDS."""
    return COMMAND_SECTIONS.get(str(entry.get("command", "")))


def group_for(action: str) -> str:
    """Which section an action belongs to; unknown actions stay visible."""
    if action in PROMOTED:
        return "COMMANDS"
    if action.startswith("navigate_"):
        return "Navigate mode"
    for title, actions in GROUPS:
        if action in actions:
            return title
    # A herdr release can add actions this list has never heard of. They belong
    # on screen, not silently dropped.
    return "Other"


# ANSI 16-colour codes only: they resolve through the terminal's own palette,
# so the popup follows whatever herdr theme is active instead of fighting it.
BOLD, CHORD, DIM, RESET = "\033[1m", "\033[36m", "\033[2m", "\033[0m"


def colour_enabled() -> bool:
    # https://no-color.org - any value means off. Piped output stays plain, so
    # grepping the list does not have to step over escape codes.
    return not os.environ.get("NO_COLOR") and sys.stdout.isatty()


def paint(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if colour_enabled() else text


# How a key name is drawn. Herdr spells these out in config; on the keyboard
# they are a single glyph. enter/tab/esc/space/backspace stay words: they are
# keys you press, not characters you can show.
KEY_SYMBOLS = {
    "slash": "/", "minus": "-", "comma": ",", "period": ".",
    "semicolon": ";", "quote": "'", "backtick": "`", "equal": "=",
    "left": "\u2190", "up": "\u2191", "right": "\u2192", "down": "\u2193",
}


def spell(chord: str) -> str:
    parts = chord.split("+")
    return "+".join(KEY_SYMBOLS.get(part, part) for part in parts)


ARROWS = ("\u2191", "\u2193", "\u2192", "\u2190")  # up, down, right, left


def collapse_arrows(shown: list[str]) -> list[str]:
    """`ctrl+\u2191 / ctrl+\u2193 / ctrl+\u2192 / ctrl+\u2190` -> `ctrl+\u2191\u2193\u2192\u2190`.

    An action bound to all four arrows is one gesture, not four bindings, and
    spelling it out four times widens the column for every other row.
    """
    if len(shown) < 2:
        return shown
    heads, tails = set(), set()
    for chord in shown:
        head, _, tail = chord.rpartition("+")
        if not head or tail not in ARROWS:
            return shown
        heads.add(head)
        tails.add(tail)
    if len(heads) != 1 or len(tails) != len(shown):
        return shown
    head = heads.pop()
    return [head + "+" + "".join(a for a in ARROWS if a in tails)]


def split_chords(chords: list[str], prefix_key: str) -> tuple[str, str]:
    """Split a binding into its one-press form and its prefix form.

    They become separate columns: the chord you press in one go is the one
    people reach for, and the prefix fallback should not push it out of line.
    """
    direct = [spell(c) for c in chords if not c.startswith("prefix+")]
    leader = [
        # Space, not +: the prefix is released before the next key.
        f"{spell(prefix_key)} {spell(c[len('prefix+'):])}" if prefix_key else spell(c)
        for c in chords
        if c.startswith("prefix+")
    ]
    return " / ".join(collapse_arrows(direct)), " / ".join(collapse_arrows(leader))


def custom_key(entry: dict, prefix_key: str = "") -> tuple[str, str]:
    """A [[keys.command]] key is one chord or a list of them, like an action."""
    chords = as_chords(entry.get("key", ""))
    return split_chords(chords, prefix_key) if chords else (str(entry.get("key", "")), "")


# Herdr names a split by the divider it draws; people think in where the new
# pane lands. Only actions whose own name misleads are listed here.
DESCRIPTIONS = {
    "split_vertical": "Split right",
    "split_horizontal": "Split down",
    # "Goto" says nothing about what opens: every agent and terminal, grouped
    # by workspace and searchable.
    "goto": "Overview",
}


def describe(action: str) -> str:
    if action in DESCRIPTIONS:
        return DESCRIPTIONS[action]
    text = re.sub(r"^navigate_", "", action).replace("_", " ")
    return text[:1].upper() + text[1:]


def entries(path: Path) -> tuple[list[tuple[str, str, str, str]], str]:
    """Every row as (section, direct chord, prefix chord, description).

    Shared by the popup and by the printed reference card in assets/, so
    both are built from one resolution of the config rather than two.
    """
    config = user_config(path)
    keys = config.get("keys", {})
    overrides = keys if isinstance(keys, dict) else {}

    resolved: list[tuple[str, list[str]]] = []
    for action, chords in default_bindings():
        if action in overrides:
            found = as_chords(overrides[action])
            # An action bound to nothing in the user config is unbound, not
            # defaulted back to herdr's value.
            chords = found if found is not None else chords
        if chords:
            resolved.append((action, chords))

    custom = [e for e in overrides.get("command", []) if isinstance(e, dict)]

    prefix_chords = next((c for a, c in resolved if a == "prefix"), [])
    prefix_key = prefix_chords[0] if prefix_chords else ""

    # Every row as (direct, prefix, description), so both chord columns can be
    # measured before anything is written.
    rows: list[tuple[str, str, str, str]] = []  # (section, direct, prefix, text)

    bound = {action: chords for action, chords in resolved if action != "prefix"}

    routed: dict[str, list[tuple[str, str, str]]] = {}
    for entry in custom:
        text = entry.get("description") or entry.get("command") or entry.get("type", "")
        direct, leader = custom_key(entry, prefix_key)
        section = command_section(entry)
        if section:
            routed.setdefault(section, []).append((direct, leader, str(text)))
        else:
            rows.append(("COMMANDS", direct, leader, str(text)))
    for action, position in sorted(PROMOTED.items(), key=lambda kv: kv[1]):
        if action not in bound:
            continue
        direct, leader = split_chords(bound[action], prefix_key)
        rows.insert(min(position, len(rows)),
                    ("COMMANDS", direct, leader, describe(action)))
    titles = [t for t, _ in GROUPS] + ["Navigate mode", "Other"]
    titles = [t for t in titles if t not in HIDDEN_SECTIONS]
    for title in titles:
        members = [a for a in bound
                   if group_for(a) == title and a not in HIDDEN_ACTIONS]
        if not members:
            continue
        order = dict(GROUPS).get(title, [])
        members.sort(key=lambda a: order.index(a) if a in order else len(order))
        for action in members:
            direct, leader = split_chords(bound[action], prefix_key)
            rows.append((title.upper(), direct, leader, describe(action)))
        for direct, leader, text in routed.pop(title, []):
            rows.append((title.upper(), direct, leader, text))

    # A routed command whose group has no herdr actions bound would otherwise
    # be dropped by the loop above, so it gets its own section rather than
    # disappearing.
    for title, entries in routed.items():
        for direct, leader, text in entries:
            rows.append((title.upper(), direct, leader, text))

    return rows, prefix_key


def render(path: Path) -> list[str]:
    rows, prefix_key = entries(path)

    w1 = max([len(r[1]) for r in rows] + [8])
    w2 = max([len(r[2]) for r in rows] + [8])

    def row(direct: str, leader: str, text: str) -> str:
        return (
            f"  {paint(f'{direct:<{w1}}', CHORD)}"
            f"  {paint(f'{leader:<{w2}}', DIM)}  {text}"
        )

    lines: list[str] = []
    lines.append(
        f"  {paint(f'{"KEYCAPS":<{w1}}', BOLD)}"
        f"  {paint(f'{"PREFIX":<{w2}}', BOLD)}  {paint('every binding in effect', DIM)}"
    )
    # No row for the prefix key itself: it is not a binding of its own, and in
    # the KEYCAPS column it read as though ctrl+b were a direct chord. Every
    # PREFIX cell already spells it out.
    lines.append("")

    section = None
    for title, direct, leader, text in rows:
        if title != section:
            if section is not None:
                lines.append("")
            lines.append(f"  {paint(title, BOLD)}")
            section = title
        lines.append(row(direct, leader, text))

    return lines


def document(path: Path) -> str:
    """The list as one plain string, for piped output.

    The popup pages render() directly and draws its own status line, so the
    key hint lives in one place: the surface where keys mean anything.
    """
    return "\n".join([""] + render(path) + [""]) + "\n"


HIDE_CURSOR, SHOW_CURSOR = "\033[?25l", "\033[?25h"


def scroll_intent(key: str) -> str:
    """One key -> a paging intent. Pure, so the key map is testable.

    Scroll keys first, then picker's shared map, which already tells a bare
    Escape from an arrow and closes on q and ctrl+c.
    """
    if not key:
        # stdin is at EOF: nothing further can arrive to dismiss the popup.
        return "cancel"
    if key in ("\x1b[6~", " ", "\x06"):
        return "page_down"
    if key in ("\x1b[5~", "b", "\x02"):
        return "page_up"
    if key in ("g", "\x1b[H", "\x1b[1~"):
        return "top"
    if key in ("G", "\x1b[F", "\x1b[4~"):
        return "bottom"
    return classify(key)


def scrolled(top: int, action: str, view: int, total: int) -> int:
    """Where the viewport lands after one key, clamped to the list. Pure."""
    last = max(0, total - view)
    if action == "top":
        return 0
    if action == "bottom":
        return last
    step = {"down": 1, "enter": 1, "up": -1,
            "page_down": view, "page_up": -view}.get(action, 0)
    return max(0, min(top + step, last))


def viewport() -> int:
    """Rows the popup actually has.

    The terminal's own size, not $LINES: a popup inherits that from the pane
    that opened it, which is a different height.
    """
    try:
        return os.get_terminal_size(sys.stdout.fileno()).lines
    except OSError:
        return 24


def frame(body: list[str], top: int, view: int) -> str:
    """One screenful, padded to `view` rows, with the status line beneath.

    Exactly as many lines as the terminal has rows, and no trailing newline,
    so drawing a frame never scrolls the top of the list away.
    """
    shown = body[top:top + view]
    shown += [""] * (view - len(shown))
    hint = "esc to close"
    if len(body) > view:
        hint = f"\u2191\u2193 to scroll \u00b7 {hint}"
    return "\033[H\033[2J" + "\r\n".join(shown + [f"  {paint(hint, DIM)}"])


def page(body: list[str]) -> None:
    """Hold the popup open until Escape, scrolling in place until then.

    less would be the obvious pager, but it cannot be told to close on
    Escape: there Escape is the prefix of an escape sequence rather than a
    key, and rebinding it needs --lesskey-src, which arrived in less 582 while
    macOS still ships 581. So the popup pages itself.
    """
    top = 0
    with raw_mode():
        sys.stdout.write(HIDE_CURSOR)
        try:
            while True:
                view = max(viewport() - 1, 1)  # the status line keeps a row
                # Re-clamp every frame: the terminal may have been resized
                # since the last one, leaving the viewport past the end.
                top = scrolled(top, "", view, len(body))
                sys.stdout.write(frame(body, top, view))
                sys.stdout.flush()
                action = scroll_intent(read_key())
                if action == "cancel":
                    return
                top = scrolled(top, action, view, len(body))
        finally:
            sys.stdout.write(SHOW_CURSOR + "\r\n")
            sys.stdout.flush()


def main() -> int:
    path = config_path()
    if sys.stdout.isatty():
        page([""] + render(path))
        return 0
    sys.stdout.write(document(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
