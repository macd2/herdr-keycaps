#!/usr/bin/env python3
"""Tell the user, once per server start, when nothing in this plugin is bound.

herdr cannot print a message for a plugin at install time: `print_install_preview`
emits only herdr's own fields, and a build command's output is piped and thrown
away unless the command fails, which aborts the install. So the first moment this
plugin can say anything is when the server starts.

The rule is deliberately strict - notify only when *no* macd2.keycaps binding
exists at all. Someone who bound a subset on purpose has set this up their way
and must not be nagged about the rest. Create `no-reminder` in the plugin's
config dir to switch it off for good.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from setup import ROOT, config_path, herdr_bin, read

PREFIX = "macd2.keycaps."
OPT_OUT = "no-reminder"
# The server is still coming up when startup hooks run, so the socket can refuse
# the first attempts. Bounded, and in a detached child, so herdr is never held up.
TRIES, GAP = 10, 1.0


def opted_out() -> bool:
    state = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    return bool(state) and (Path(state) / OPT_OUT).exists()


def bound_count(cfg: dict) -> int:
    """How many of this plugin's actions a key can reach."""
    commands = cfg.get("keys", {}).get("command", [])
    return sum(1 for block in commands
               if str(block.get("command", "")).startswith(PREFIX))


def notify() -> bool:
    body = f"Nothing is bound yet. Run:  python3 {ROOT / 'setup.py'}"
    for attempt in range(TRIES):
        try:
            done = subprocess.run(
                [herdr_bin(), "notification", "show",
                 "Keycaps: no keybindings", "--body", body,
                 "--position", "top-right", "--sound", "none"],
                capture_output=True, text=True, timeout=10,
            )
            if done.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            pass
        if attempt < TRIES - 1:
            time.sleep(GAP)
    return False


def detach() -> None:
    """Startup hooks are one-shot: hand herdr back the process immediately."""
    if os.fork():
        sys.exit(0)
    os.setsid()
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)


def main() -> int:
    if "--foreground" not in sys.argv:
        detach()
    if opted_out():
        return 0
    try:
        cfg = read(config_path())
    except (OSError, tomllib.TOMLDecodeError):
        # A config herdr itself will complain about is not ours to report on.
        return 0
    if bound_count(cfg):
        return 0
    print("no keycaps binding found; notifying")
    notify()
    # A startup hook that exits non-zero is noise in herdr's plugin log for
    # something the user can do nothing about, so a failed notify stays quiet.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
