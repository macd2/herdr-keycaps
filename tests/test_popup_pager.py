#!/usr/bin/env python3
"""The popup must stay open until dismissed, and must exit cleanly on q.

A popup pane closes as soon as its command exits, so a pager that quits on a
screenful would flash the popup open and shut. This drives keycaps.py
on a real pty, the way the popup does, and cleans the pty up either way.
"""

import fcntl
import os
import pty
import select
import signal
import struct
import sys
import termios
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 5.0


def drain(fd, deadline):
    out = b""
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if not ready:
            continue
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    return out


def main() -> int:
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        # A popup is a large surface; the default 80x24 pty would page the
        # list and hide the bindings this test checks for.
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 60, 100, 0, 0))
        os.chdir(ROOT)
        os.execvp(sys.executable, [sys.executable, "keycaps.py"])

    try:
        screen = drain(fd, time.monotonic() + 1.5)

        # Still running means the pager held the popup open.
        waited, _ = os.waitpid(pid, os.WNOHANG)
        assert waited == 0, "keycaps exited on its own; popup would flash shut"
        assert b"KEYCAPS" in screen, "header missing from popup"
        # Arrow keys render as glyphs, so this also proves UTF-8 survives the pty.
        assert "alt+\u2190".encode() in screen, "alt bindings missing from popup"
        # The popup is a tty, so the list must arrive coloured.
        assert b"\x1b[36m" in screen, "chords not coloured in the popup"
        assert b"\x1b[1m" in screen, "section headings not bold in the popup"

        os.write(fd, b"q")
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited:
                assert os.waitstatus_to_exitcode(status) == 0, "non-zero exit on q"
                print("PASS: popup stayed open, closed on q")
                return 0
            time.sleep(0.1)
        raise AssertionError("pager did not exit after q")
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())
