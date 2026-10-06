#!/usr/bin/env python3
"""The action shim must ask herdr for the popup pane, by plugin and entrypoint.

Running the real command would leave a modal popup open in the live session, so
this points HERDR_BIN_PATH at a stub that records its argv instead.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STUB = """#!/bin/sh
printf '%s\\n' "$@" > "$ARGV_LOG"
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "herdr-stub"
        stub.write_text(STUB)
        stub.chmod(0o755)
        log = tmp / "argv"

        env = {**os.environ, "HERDR_BIN_PATH": str(stub), "ARGV_LOG": str(log)}
        result = subprocess.run(
            [sys.executable, "show.py"], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"show.py failed: {result.stderr}"

        argv = log.read_text().split()
        assert argv[:3] == ["plugin", "pane", "open"], argv
        assert "--plugin" in argv and "--entrypoint" in argv, argv
        assert argv[argv.index("--plugin") + 1] == "macd2.keycaps", argv
        assert argv[argv.index("--entrypoint") + 1] == "keys", argv
        # Placement is deliberately absent: the CLI has no popup value, so the
        # manifest's placement = "popup" must be the one that wins.
        assert "--placement" not in argv, argv

    print("PASS: show.py opens the keycaps pane with manifest placement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
