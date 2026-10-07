#!/usr/bin/env python3
"""The gate has to refuse, leave the file alone, and say so to an agent.

A refusal is only worth having if it is reachable, so each case here is a shape
that really parses as TOML and really defeats line surgery. The assertions that
matter are the two the user cares about: the file on disk is unchanged, and the
message tells whatever is reading the terminal to ask its owner rather than
editing the config itself.
"""

import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import harness

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import guard  # noqa: E402

# keys.command as an inline array: parses, but there is no [[keys.command]]
# block to delete, so a line-based edit would silently do nothing.
INLINE = ('onboarding = false\n'
          'keys.command = [{key = "alt+h", type = "plugin_action", '
          'command = "macd2.keycaps.show"}]\n')
# An array spread over several lines: removing only the first line would leave
# the rest behind as broken TOML.
SPREAD = ('[keys]\nzoom = [\n  "prefix+z",\n  "alt+z",\n]\n\n'
          '[[keys.command]]\nkey = "alt+h"\ntype = "plugin_action"\n'
          'command = "macd2.keycaps.show"\n')


def run(script: str, cfg: Path, *args) -> tuple[int, str]:
    done = subprocess.run(
        [sys.executable, script, "--yes", *args], cwd=ROOT, timeout=30,
        capture_output=True, text=True,
        env=harness.clean_env(HERDR_CONFIG_PATH=str(cfg)))
    return done.returncode, done.stdout + done.stderr


def assert_refused(code: int, out: str, cfg: Path, before: str) -> None:
    assert code == 1, f"a refusal must exit 1, got {code}:\n{out}"
    assert guard.BANNER in out, out
    assert "reason:" in out, out
    assert "TO ANY AGENT READING THIS" in out, out
    assert "Ask your owner for permission first" in out, out
    assert "Nothing was written" in out, out
    assert cfg.read_text() == before, "the config was changed despite refusing"


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # --- an inline keys.command array ---------------------------------
        inline = tmp / "inline.toml"
        inline.write_text(INLINE)
        tomllib.loads(INLINE)  # the fixture must be real TOML, or it proves nothing
        code, out = run("uninstall.py", inline)
        assert_refused(code, out, inline, INLINE)
        assert "inline array" in out or "dotted key" in out, out

        # --- a value spread over several lines ----------------------------
        spread = tmp / "spread.toml"
        spread.write_text(SPREAD)
        tomllib.loads(SPREAD)
        code, out = run("uninstall.py", spread, "--also-direct-layer")
        assert_refused(code, out, spread, SPREAD)
        assert "spans more than one line" in out, out
        # Without touching the [keys] layer the same file is fine to edit.
        code, out = run("uninstall.py", spread)
        assert code == 0, out
        assert "macd2.keycaps" not in spread.read_text(), spread.read_text()
        assert 'zoom = [' in spread.read_text(), "the spread value was damaged"

        # --- setup.py refuses the same shape ------------------------------
        also = tmp / "also.toml"
        also.write_text(INLINE)
        code, out = run("setup.py", also)
        assert_refused(code, out, also, INLINE)

        # --- the semantic gate catches an edit that strays -----------------
        before = tomllib.loads('[keys]\nzoom = ["alt+z"]\n')
        want = guard.expected(before, {"new_tab": ["alt+t"]}, [], [], [])
        assert guard.unexplained_change(
            '[keys]\nzoom = ["alt+z"]\nnew_tab = ["alt+t"]\n', want) is None
        # ...a stray change to an untouched table
        assert "[theme] changed" in str(guard.unexplained_change(
            '[theme]\nname = "x"\n[keys]\nzoom = ["alt+z"]\nnew_tab = ["alt+t"]\n',
            want))
        # ...a value that came out different from the intent
        assert "ended up as" in str(guard.unexplained_change(
            '[keys]\nzoom = ["alt+9"]\nnew_tab = ["alt+t"]\n', want))
        # ...and output that is not TOML at all
        assert "not valid TOML" in str(guard.unexplained_change("[keys\n", want))

        # --- an empty [keys] table and no [keys] are the same thing --------
        assert guard.normalise(tomllib.loads("[keys]\n")) == {}
        assert guard.unexplained_change("", guard.expected({}, {}, [], [], [])) is None

    print("PASS: refuses the shapes it cannot edit, writes nothing, tells the agent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
