#!/usr/bin/env python3
"""Merge the keymap in bindings.toml into the user's herdr config, once.

A herdr plugin ships behaviour, never keys: the manifest has no field for a
binding and `herdr plugin install` never touches config.toml, so a fresh machine
has every action registered and no key that reaches any of them. That looks
exactly like a broken install, which is why this exists.

The file is edited as text, not as a parsed document. tomllib decides what is
missing; the writing is line insertion, so the comments, ordering and spacing in
the owner's own config survive a run. Anything already bound is left alone - a
key the user chose outranks one this plugin suggests - so running twice changes
nothing.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path

import guard
from keycaps import config_path, herdr_bin

ROOT = Path(__file__).resolve().parent
BINDINGS = ROOT / "bindings.toml"
# `[keys]` with an optional trailing comment, and nothing else on the line.
KEYS_HEADER = re.compile(r"^\[keys\]\s*(#.*)?$")
KEYS_SUBTABLE = re.compile(r"^\[\[?keys[.\]]")
MARK = "# --- added by keycaps setup.py"
# A skip is either "you had it" - noise on a repeat run - or a chord this
# plugin wanted and cannot have, which the user has to see every time.
PRESENT, CONFLICT = "present", "conflict"


def chords(value) -> list[str]:
    """A [keys] value is one chord or a list of them."""
    return [value] if isinstance(value, str) else list(value)


def toml_value(value) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    return "[" + ", ".join(f'"{v}"' for v in value) + "]"


def wanted() -> tuple[dict, list[dict]]:
    """The keymap this plugin is built around, as data."""
    data = tomllib.loads(BINDINGS.read_text())
    keys = {k: v for k, v in data["keys"].items() if k != "command"}
    return keys, data["keys"]["command"]


def read(path: Path) -> dict:
    """The user's config, or {} when there is not one yet."""
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text())


def taken(cfg: dict) -> dict[str, str]:
    """Every chord already spoken for -> what holds it.

    Both halves of a herdr config can own a chord: a [keys] action and a
    [[keys.command]] block. A suggestion that lands on either is a conflict.
    """
    held: dict[str, str] = {}
    keys = cfg.get("keys", {})
    for name, value in keys.items():
        if name == "command":
            continue
        for chord in chords(value):
            held.setdefault(chord, name)
    for block in keys.get("command", []):
        if block.get("key"):
            held.setdefault(block["key"], block.get("command", "a command"))
    return held


def plan(cfg: dict, want_keys: dict, want_cmds: list[dict], only_plugin_keys: bool):
    """What to add, and why each skipped item was skipped."""
    held = taken(cfg)
    keys = cfg.get("keys", {})
    mine = {k for k in keys if k != "command"}
    bound = {b.get("command") for b in keys.get("command", [])}

    add_keys: dict = {}
    skip_keys: list[tuple[str, str, str]] = []
    if not only_plugin_keys:
        for name, value in want_keys.items():
            if name in mine:
                skip_keys.append((name, "you already set it", PRESENT))
                continue
            clash = [c for c in chords(value) if c in held]
            if clash:
                skip_keys.append((name, f"{clash[0]} is taken by {held[clash[0]]}", CONFLICT))
                continue
            add_keys[name] = value
            for chord in chords(value):
                held[chord] = name

    add_cmds: list[dict] = []
    skip_cmds: list[tuple[str, str, str]] = []
    for block in want_cmds:
        if block["command"] in bound:
            skip_cmds.append((block["command"], "already bound", PRESENT))
        elif block["key"] in held:
            skip_cmds.append((block["command"],
                              f"{block['key']} is taken by {held[block['key']]}",
                              CONFLICT))
        else:
            add_cmds.append(block)
            held[block["key"]] = block["command"]
    return add_keys, add_cmds, skip_keys, skip_cmds


def key_lines(add_keys: dict) -> list[str]:
    width = max(len(name) for name in add_keys)
    return [f"{name.ljust(width)} = {toml_value(value)}"
            for name, value in add_keys.items()]


def command_blocks(add_cmds: list[dict]) -> list[str]:
    out: list[str] = []
    for block in add_cmds:
        out += ["[[keys.command]]",
                f'key = "{block["key"]}"',
                f'type = "{block["type"]}"',
                f'command = "{block["command"]}"']
        if block.get("description"):
            out.append(f'description = "{block["description"]}"')
        out.append("")
    return out


def merged(text: str, add_keys: dict, add_cmds: list[dict]) -> str:
    """The config text with the missing pieces inserted, nothing else moved."""
    lines = text.splitlines()
    if add_keys:
        block = [MARK] + key_lines(add_keys)
        at = next((i for i, line in enumerate(lines)
                   if KEYS_HEADER.match(line.strip())), None)
        if at is not None:
            lines[at + 1:at + 1] = block
        else:
            # A new [keys] table has to come before any [[keys.command]]:
            # placing it after would redefine a table TOML already created.
            at = next((i for i, line in enumerate(lines)
                       if KEYS_SUBTABLE.match(line.strip())), len(lines))
            lines[at:at] = ["[keys]"] + block + [""]
    if add_cmds:
        lines += ["", MARK] + command_blocks(add_cmds)
    return "\n".join(lines).rstrip() + "\n"


def report(add_keys, add_cmds, skip_keys, skip_cmds) -> None:
    """Adds and conflicts in full; "you already had it" as a count.

    A second run skips everything, and 34 identical lines would bury the one
    line that matters - a chord this plugin wanted and could not have.
    """
    for name, value in add_keys.items():
        print(f"  + [keys] {name} = {toml_value(value)}")
    for block in add_cmds:
        print(f"  + {block['key']}  ->  {block['command']}")
    skipped = skip_keys + skip_cmds
    for name, why, _ in [s for s in skipped if s[2] == CONFLICT]:
        print(f"  ! {name} left alone: {why}")
    present = sum(1 for s in skipped if s[2] == PRESENT)
    if present:
        print(f"  . {present} already in your config, left alone")


def run_herdr() -> None:
    """Validate and reload - skipped when pointed at a config herdr is not reading."""
    if os.environ.get("HERDR_CONFIG_PATH"):
        print("  HERDR_CONFIG_PATH is set, so herdr was not asked to reload.")
        return
    for args, label in ((["config", "check"], "config check"),
                        (["server", "reload-config"], "reload")):
        try:
            done = subprocess.run([herdr_bin(), *args], capture_output=True,
                                  text=True, timeout=15)
            print(f"  herdr {label}: {(done.stdout or done.stderr).strip() or done.returncode}")
        except (OSError, subprocess.SubprocessError) as error:
            print(f"  herdr {label} could not run ({error}); do it yourself")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan and write nothing")
    parser.add_argument("--only-plugin-keys", action="store_true",
                        help="skip the [keys] direct layer, bind this plugin only")
    parser.add_argument("-y", "--yes", action="store_true", help="do not ask")
    args = parser.parse_args()

    path = config_path()
    try:
        cfg = read(path)
    except tomllib.TOMLDecodeError as error:
        print(f"{path} does not parse, so nothing was changed: {error}", file=sys.stderr)
        return 1

    want_keys, want_cmds = wanted()
    add_keys, add_cmds, skip_keys, skip_cmds = plan(cfg, want_keys, want_cmds,
                                                   args.only_plugin_keys)
    print(f"herdr config: {path}")
    report(add_keys, add_cmds, skip_keys, skip_cmds)

    if not add_keys and not add_cmds:
        print("Nothing to do: this config already has the keymap.")
        return 0
    if args.dry_run:
        print("Dry run, nothing written.")
        return 0
    if not args.yes and sys.stdin.isatty():
        if input("Write these to your config? [y/N] ").strip().lower() != "y":
            print("Left alone.")
            return 0

    text = path.read_text() if path.exists() else ""
    remedy = [
        f"open {path} and add the lines listed above by hand",
        f"they are also in {BINDINGS}, which is the keymap this plugin expects",
        "then run: herdr server reload-config",
    ]

    # Checked before the file is opened for writing, so a refusal leaves nothing
    # to undo. Editing someone's whole herdr setup wrongly is worse than not
    # editing it at all.
    reason = guard.unsupported_shape(text, cfg) if text else None
    if reason:
        return guard.refuse(reason, path, remedy)

    new = merged(text, add_keys, add_cmds)
    want = guard.expected(cfg, add_keys, [], add_cmds, [])
    reason = guard.unexplained_change(new, want)
    if reason:
        return guard.refuse(reason, path, remedy)

    backup = None
    if text:
        backup = path.with_suffix(f".toml.bak-{datetime.now():%Y%m%dT%H%M%S}")
        shutil.copy2(path, backup)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new)
    print(f"Written. Backup: {backup}" if backup else "Written (new file).")
    run_herdr()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
