#!/usr/bin/env python3
"""The popup must stay open until dismissed, and must close on Escape.

A popup pane closes as soon as its command exits, so a pager that quits on a
screenful would flash the popup open and shut. This drives keycaps.py on a
real pty, the way the popup does, and cleans the pty up either way.
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


def run(dismiss: bytes, rows: int = 60) -> bytes:
    """Open the popup, dismiss it with `dismiss`, return what it drew.

    Fails if it exits before the key arrives, or does not exit after it.
    """
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        # A popup is a large surface; the default 80x24 pty would page the
        # list and hide the bindings this test checks for.
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, 100, 0, 0))
        os.chdir(ROOT)
        os.execvp(sys.executable, [sys.executable, "keycaps.py"])

    try:
        screen = drain(fd, time.monotonic() + 1.5)

        # Still running means the pager held the popup open.
        waited, _ = os.waitpid(pid, os.WNOHANG)
        assert waited == 0, "keycaps exited on its own; popup would flash shut"

        os.write(fd, dismiss)
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited:
                code = os.waitstatus_to_exitcode(status)
                assert code == 0, f"non-zero exit on {dismiss!r}: {code}"
                return screen
            time.sleep(0.1)
        raise AssertionError(f"pager did not exit after {dismiss!r}")
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass
        os.close(fd)


def main() -> int:
    # Escape is the key the popup is opened and closed with; a bare one must
    # not be mistaken for the start of an arrow sequence.
    screen = run(b"\x1b")
    assert b"KEYCAPS" in screen, "header missing from popup"
    # Arrow keys render as glyphs, so this also proves UTF-8 survives the pty.
    assert "alt+←".encode() in screen, "alt bindings missing from popup"
    # The popup is a tty, so the list must arrive coloured.
    assert b"\x1b[36m" in screen, "chords not coloured in the popup"
    assert b"\x1b[1m" in screen, "section headings not bold in the popup"
    assert b"esc to close" in screen, "close hint missing from the status line"

    # q closes it too, and on a terminal too short for the list the status
    # line says so instead of leaving the rest of it unreachable.
    short = run(b"q", rows=12)
    assert "↑↓ to scroll".encode() in short, "no scroll hint when clipped"
    assert short.count(b"KEYCAPS") == 1, "clipped popup drew more than a screen"

    print("PASS: popup stayed open, closed on esc and on q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
