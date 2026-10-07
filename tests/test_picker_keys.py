#!/usr/bin/env python3
"""Key handling, and the picker driven on a real pty.

Esc alone cancels while arrows arrive as Esc [ A, so the two must not be
confused. The pty half drives the list the way a person does and checks which
tab the move ends up targeting - a stub herdr stands in for the session, so
nothing in the live one moves.
"""

import fcntl
import json
import os
import pty
import select
import signal
import struct
import sys
import tempfile
import termios
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import harness  # noqa: E402
import picker  # noqa: E402

TABS = {"result": {"tabs": [
    {"tab_id": "w7:t1", "label": "Claude1", "pane_count": 2, "number": 1},
    {"tab_id": "w7:t3", "label": "Hermes", "pane_count": 2, "number": 3},
    {"tab_id": "w7:t4", "label": "Notes", "pane_count": 1, "number": 4},
]}}
SPACES = {"result": {"workspaces": [
    {"workspace_id": "w7", "label": "Redesign"},
]}}
PANE = {"result": {"pane": {"pane_id": "w7:pA", "tab_id": "w7:t3"}}}

STUB = """#!/bin/sh
case "$1 $2" in
  "pane current") cat "$FIXTURES/pane.json" ;;
  "tab list")     cat "$FIXTURES/tabs.json" ;;
  "workspace list") cat "$FIXTURES/spaces.json" ;;
  "pane move")    printf '%s\\n' "$@" > "$ARGV_LOG"; echo '{"result":{"type":"ok"}}' ;;
esac
"""


def test_classify():
    assert picker.classify("\x1b[A") == "up"
    assert picker.classify("\x1b[B") == "down"
    assert picker.classify("k") == "up"
    assert picker.classify("j") == "down"
    assert picker.classify("\r") == "enter"
    # Esc on its own must cancel, not be mistaken for an arrow prefix.
    assert picker.classify("\x1b") == "cancel"
    assert picker.classify("q") == "cancel"
    assert picker.classify("2") == "2"
    assert picker.classify("z") == ""


def drive(keys: list[bytes], tmp: Path) -> tuple[bytes, list[str]]:
    # A terminal delivers an escape sequence in one write, so each element is
    # written whole; and a stale log would read as this run's move.
    log = tmp / "argv"
    log.unlink(missing_ok=True)
    pid, fd = pty.fork()
    if pid == 0:
        env = harness.clean_env(
            HERDR_BIN_PATH=str(tmp / "herdr-stub"), FIXTURES=str(tmp),
            ARGV_LOG=str(log), TERM="xterm-256color")
        os.environ.clear()
        os.environ.update(env)
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        os.chdir(ROOT)
        os.execvp(sys.executable, [sys.executable, "picker.py"])

    screen = b""
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and b"q to cancel" not in screen:
            if select.select([fd], [], [], 0.2)[0]:
                screen += os.read(fd, 65536)
        # The prompt appears a moment before picker.py puts the tty in raw
        # mode. Keys written into canonical mode get line-buffered and the
        # escape sequence arrives mangled, so let it settle first.
        time.sleep(0.1)
        for key in keys:
            os.write(fd, key)
            time.sleep(0.25)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if os.waitpid(pid, os.WNOHANG)[0]:
                break
            if select.select([fd], [], [], 0.2)[0]:
                screen += os.read(fd, 65536)
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass
        os.close(fd)
    argv = log.read_text().split() if log.exists() else []
    return screen, argv


def main() -> int:
    test_classify()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "tabs.json").write_text(json.dumps(TABS))
        (tmp / "spaces.json").write_text(json.dumps(SPACES))
        (tmp / "pane.json").write_text(json.dumps(PANE))
        stub = tmp / "herdr-stub"
        stub.write_text(STUB)
        stub.chmod(0o755)

        # The pane sits in w7:t3, so under the "Redesign" heading the
        # selectable rows are [w7:t1, w7:t4, new tab here, new workspace].
        # Down once then Enter must take the second, w7:t4 - the heading is
        # skipped, not counted.
        screen, argv = drive([b"\x1b[B", b"\r"], tmp)
        assert b"MOVE PANE" in screen, "picker did not draw"
        assert b"Claude1" in screen and b"Notes" in screen, "tabs missing from list"
        assert "--tab" in argv and argv[argv.index("--tab") + 1] == "w7:t4", argv
        assert "--split" in argv, f"--split is mandatory with --tab: {argv}"

        # A number jumps straight there without Enter.
        _, argv = drive([b"1"], tmp)
        assert argv[argv.index("--tab") + 1] == "w7:t1", argv

        # q leaves without moving anything.
        _, argv = drive([b"q"], tmp)
        assert argv == [], f"cancel still moved a pane: {argv}"

    print("PASS: arrows, numbers and cancel all route to the right tab")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
