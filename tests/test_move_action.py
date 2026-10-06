#!/usr/bin/env python3
"""The action shim must open the picker pane, by plugin and entrypoint.

Running the real command would leave a modal popup in the live session, so
HERDR_BIN_PATH points at a stub that records its argv.
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
        result = subprocess.run([sys.executable, "move.py"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, f"move.py failed: {result.stderr}"

        argv = log.read_text().split()
        assert argv[:3] == ["plugin", "pane", "open"], argv
        assert argv[argv.index("--plugin") + 1] == "macd2.keycaps", argv
        assert argv[argv.index("--entrypoint") + 1] == "picker", argv
        # Manifest placement = "popup" must win; the CLI has no popup value.
        assert "--placement" not in argv, argv

    print("PASS: move.py opens the picker pane with manifest placement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
