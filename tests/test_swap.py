#!/usr/bin/env python3
"""Direction parsing, and the argv each action actually sends.

One script backs four manifest actions, so the mapping from action id to
direction is the thing that decides which way a real pane jumps. A stub herdr
records the call instead of moving anything.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import harness  # noqa: E402
import swap  # noqa: E402

# Behaves like herdr: answers `pane current`, records each swap argv, and
# reports changed=true once then false, so the wrap path terminates.
STUB = r"""#!/bin/sh
case "$1 $2" in
  "pane current")
    echo '{"result":{"pane":{"pane_id":"w7:pA","tab_id":"w7:t3"}}}' ;;
  "pane swap")
    printf '%s\n' "$@" >> "$ARGV_LOG"
    if [ -f "$ARGV_LOG.done" ]; then
      echo '{"result":{"swap":{"changed":false}}}'
    else
      : > "$ARGV_LOG.done"
      echo '{"result":{"swap":{"changed":true}}}'
    fi ;;
esac
"""


def main() -> int:
    for name in ("left", "down", "up", "right"):
        assert swap.direction(f"swap-{name}") == name
    # Anything not a known direction must be refused, not guessed at.
    assert swap.direction("swap-sideways") is None
    assert swap.direction("move") is None
    assert swap.direction("") is None

    # Every direction in the manifest must be one the script accepts, or the
    # binding would fire and do nothing.
    manifest = (ROOT / "herdr-plugin.toml").read_text()
    declared = {line.split('"')[1] for line in manifest.splitlines()
                if line.startswith("id = ") and '"swap-' in line}
    assert declared == {f"swap-{d}" for d in swap.DIRECTIONS}, declared

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "herdr-stub"
        stub.write_text(STUB)
        stub.chmod(0o755)
        log = tmp / "argv"

        env = harness.clean_env(HERDR_BIN_PATH=str(stub), ARGV_LOG=str(log),
                                HERDR_PLUGIN_ACTION_ID="swap-up")
        result = subprocess.run([sys.executable, "swap.py"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        argv = log.read_text().split()
        # Acts on a resolved pane id, not --current: focus can follow a swap.
        assert argv[:2] == ["pane", "swap"], argv
        assert argv[argv.index("--pane") + 1] == "w7:pA", argv
        assert argv[argv.index("--direction") + 1] == "up", argv

        # An unknown action must fail loudly rather than swap some default way.
        log.unlink()
        Path(f"{log}.done").unlink(missing_ok=True)
        env["HERDR_PLUGIN_ACTION_ID"] = "swap-nowhere"
        result = subprocess.run([sys.executable, "swap.py"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 1, "unknown direction should fail"
        assert not log.exists(), "unknown direction still called herdr"

    # --- wrapping ---------------------------------------------------------
    # A row of panes as positions in a list; step() swaps with the neighbour.
    def row_stepper(order, pane):
        def step(_pane, where):
            i = order.index(pane)
            j = i - 1 if where in ("left", "up") else i + 1
            if j < 0 or j >= len(order):
                return False
            order[i], order[j] = order[j], order[i]
            return True
        return step

    order = ["A", "B", "C"]
    assert swap.cycle(row_stepper(order, "A"), "A", "right") == "moved"
    assert order == ["B", "A", "C"], order

    # At the right edge, the pane walks back to the far left: a closed cycle,
    # not a dead stop.
    order = ["B", "C", "A"]
    assert swap.cycle(row_stepper(order, "A"), "A", "right") == "wrapped"
    assert order == ["A", "B", "C"], order

    # And the same the other way.
    order = ["A", "B", "C"]
    assert swap.cycle(row_stepper(order, "A"), "A", "left") == "wrapped"
    assert order == ["B", "C", "A"], order

    # One pane on its own must not loop forever or claim it moved.
    solo = ["A"]
    assert swap.cycle(row_stepper(solo, "A"), "A", "right") == "alone"
    assert solo == ["A"], solo

    # The bound holds even if a step always claims success.
    calls = {"n": 0}
    def never_settles(_pane, _where):
        calls["n"] += 1
        return calls["n"] != 1   # first call fails, then always "moves"
    assert swap.cycle(never_settles, "A", "right", limit=8) == "wrapped"
    assert calls["n"] == 9, calls

    print("PASS: directions map, unknown ones refuse, edges wrap as a cycle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
