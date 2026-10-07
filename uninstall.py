#!/usr/bin/env python3
"""Take this plugin's keybindings back out of the user's herdr config.

`herdr plugin uninstall macd2.keycaps` removes the code and nothing else, so the
[[keys.command]] blocks pointing at macd2.keycaps.* stay behind as bindings to a
plugin that is gone. Run this first - afterwards the plugin directory, and this
script with it, no longer exists.

Only this plugin's own bindings go by default. The [keys] layer setup.py may have
written binds *herdr's* actions, which keep working with the plugin gone, so
removing it would break a working config to tidy up. --also-direct-layer takes it
too, and only where the value still matches bindings.toml: anything retuned since
is the user's own and stays.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tomllib
from datetime import datetime
from pathlib import Path

import guard
from setup import MARK, config_path, read, toml_value, wanted

PREFIX = "macd2.keycaps."
# A table header ends the block above it. Nothing else does.
TABLE = "["


def ours(block: dict) -> bool:
    return str(block.get("command", "")).startswith(PREFIX)


def plan(cfg: dict, also_direct: bool) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """Which plugin bindings and which [keys] entries to drop, and what stays."""
    keys = cfg.get("keys", {})
    drop_cmds = [b["command"] for b in keys.get("command", []) if ours(b)]

    want_keys, _ = wanted()
    drop_keys: list[str] = []
    kept: list[tuple[str, str]] = []
    if also_direct:
        for name, value in want_keys.items():
            if name not in keys:
                continue
            if keys[name] == value:
                drop_keys.append(name)
            else:
                kept.append((name, "you changed it since"))
    return drop_cmds, drop_keys, kept


def strip_command_blocks(lines: list[str]) -> list[str]:
    """Drop every [[keys.command]] block whose command is ours, header included."""
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip() == "[[keys.command]]":
            # The block is the header and its `key = value` lines, and stops at
            # the first blank or comment. Running to the next table header would
            # swallow a comment that introduces whatever comes after - deleting
            # someone else's note to tidy up ours.
            end = index + 1
            while end < len(lines):
                nxt = lines[end].strip()
                if not nxt or nxt.startswith("#") or nxt.startswith(TABLE):
                    break
                end += 1
            body = "\n".join(lines[index:end])
            if f'"{PREFIX}' in body and "command" in body:
                index = end
                continue
            out += lines[index:end]
            index = end
            continue
        out.append(line)
        index += 1
    return out


def strip_key_lines(lines: list[str], drop_keys: list[str]) -> list[str]:
    """Drop `name = ...` lines in [keys] for the names given."""
    if not drop_keys:
        return lines
    wanted_names = set(drop_keys)
    out: list[str] = []
    in_keys = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(TABLE):
            in_keys = stripped == "[keys]"
            out.append(line)
            continue
        name = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if in_keys and name in wanted_names:
            continue
        out.append(line)
    return out


def tidy(lines: list[str]) -> list[str]:
    """Remove the markers setup.py left, any [keys] it emptied, and blank runs."""
    out: list[str] = []
    for index, line in enumerate(lines):
        if line.strip() == MARK.strip():
            rest = lines[index + 1:]
            following = next((r for r in rest if r.strip()), "")
            # A marker whose lines are gone would otherwise label the next
            # thing along. What it can legitimately introduce is `name = value`;
            # EOF, a table header or the other marker all mean it is orphaned.
            if (not following
                    or following.lstrip().startswith(TABLE)
                    or following.strip() == MARK.strip()):
                continue
        if line.strip() == "[keys]":
            rest = lines[index + 1:]
            body = []
            for item in rest:
                if item.lstrip().startswith(TABLE):
                    break
                body.append(item)
            if not any(b.strip() and b.strip() != MARK.strip() for b in body):
                continue
        out.append(line)
    text = "\n".join(out)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.rstrip().splitlines()


def removed(text: str, drop_keys: list[str]) -> str:
    lines = tidy(strip_key_lines(strip_command_blocks(text.splitlines()), drop_keys))
    return "\n".join(lines).rstrip() + "\n" if lines else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would go and write nothing")
    parser.add_argument("--also-direct-layer", action="store_true",
                        help="also drop the [keys] entries setup.py wrote")
    parser.add_argument("-y", "--yes", action="store_true", help="do not ask")
    args = parser.parse_args()

    path = config_path()
    try:
        cfg = read(path)
    except tomllib.TOMLDecodeError as error:
        print(f"{path} does not parse, so nothing was changed: {error}", file=sys.stderr)
        return 1

    drop_cmds, drop_keys, kept = plan(cfg, args.also_direct_layer)
    print(f"herdr config: {path}")
    for command in drop_cmds:
        print(f"  - {command}")
    for name in drop_keys:
        print(f"  - [keys] {name} = {toml_value(cfg['keys'][name])}")
    for name, why in kept:
        print(f"  ! [keys] {name} kept: {why}")

    if not drop_cmds and not drop_keys:
        print("Nothing to do: this config has none of this plugin's bindings.")
        return 0
    if args.dry_run:
        print("Dry run, nothing written.")
        return 0
    if not args.yes and sys.stdin.isatty():
        if input("Remove these from your config? [y/N] ").strip().lower() != "y":
            print("Left alone.")
            return 0

    text = path.read_text()
    remedy = [
        f"in {path}, remove the {len(drop_cmds)} keys.command entr"
        f"{'y' if len(drop_cmds) == 1 else 'ies'} whose command starts with "
        '"macd2.keycaps." - in whatever form they are written, and nothing else',
        "leave the [keys] table alone: it binds herdr's own actions, which keep "
        "working once this plugin is gone",
        "then run: herdr plugin uninstall macd2.keycaps",
    ]

    # Everything is checked before the file is opened for writing, so a refusal
    # leaves nothing to undo.
    reason = (guard.unsupported_shape(text, cfg)
              or guard.multiline_values(text, drop_keys))
    if reason:
        return guard.refuse(reason, path, remedy)

    new = removed(text, drop_keys)
    want = guard.expected(cfg, {}, drop_keys, [], drop_cmds)
    reason = guard.unexplained_change(new, want)
    if reason:
        return guard.refuse(reason, path, remedy)

    backup = path.with_suffix(f".toml.bak-{datetime.now():%Y%m%dT%H%M%S}")
    shutil.copy2(path, backup)
    path.write_text(new)
    print(f"Removed. Backup: {backup}")
    print("Now run:  herdr plugin uninstall macd2.keycaps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
