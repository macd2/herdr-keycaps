#!/usr/bin/env python3
"""The reminder must fire exactly once on an unset-up box, and never otherwise.

A startup hook runs on every server start, so a false positive is a notification
the user sees forever and cannot act on - the failure that matters here is not
"did it notify" but "did it stay quiet when it should". A stub herdr records the
call instead of putting anything on screen.
"""

import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import harness

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import setup as setup_mod  # noqa: E402

# Records the argv of `herdr notification show` and nothing else.
STUB = """#!/bin/sh
case "$1 $2" in
  "notification show") printf '%s\\n' "$@" >> "$ARGV_LOG" ;;
esac
"""
STOCK = 'onboarding = false\n\n[theme]\nname = "catppuccin"\n'


def run(tmp: Path, cfg: Path, state: Path | None = None) -> list[str]:
    log = tmp / "argv"
    log.unlink(missing_ok=True)
    env = {"HERDR_BIN_PATH": str(tmp / "herdr-stub"), "ARGV_LOG": str(log),
           "HERDR_CONFIG_PATH": str(cfg)}
    if state:
        env["HERDR_PLUGIN_CONFIG_DIR"] = str(state)
    done = subprocess.run(
        [sys.executable, "remind.py", "--foreground"], cwd=ROOT, timeout=30,
        capture_output=True, text=True, env=harness.clean_env(**env))
    assert done.returncode == 0, f"a startup hook must never fail: {done.stderr}"
    return log.read_text().split("\n") if log.exists() else []


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "herdr-stub"
        stub.write_text(STUB)
        stub.chmod(0o755)

        # --- a box that installed and never ran setup.py ------------------
        stock = tmp / "stock.toml"
        stock.write_text(STOCK)
        argv = run(tmp, stock)
        assert argv, "nothing bound and no notification"
        joined = "\n".join(argv)
        assert "notification" in joined and "show" in joined, argv
        # The body has to carry the command, not just say something is wrong.
        assert "setup.py" in joined, argv
        assert str(ROOT) in joined, f"the body must name the real path: {argv}"

        # --- the config this plugin's own setup.py writes ------------------
        done = tmp / "done.toml"
        done.write_text(STOCK)
        subprocess.run([sys.executable, "setup.py", "--yes"], cwd=ROOT, timeout=30,
                       capture_output=True, text=True,
                       env=harness.clean_env(HERDR_CONFIG_PATH=str(done)))
        assert setup_mod.read(done)["keys"]["command"], "setup.py wrote nothing"
        assert run(tmp, done) == [], "nagged a box that is already set up"

        # --- a subset bound on purpose is a choice, not a problem ----------
        subset = tmp / "subset.toml"
        subset.write_text(STOCK + '\n[[keys.command]]\nkey = "alt+j"\n'
                          'type = "plugin_action"\ncommand = "macd2.keycaps.even"\n')
        assert run(tmp, subset) == [], "nagged someone who bound a subset"

        # --- another plugin's bindings are not ours ------------------------
        other = tmp / "other.toml"
        other.write_text(STOCK + '\n[[keys.command]]\nkey = "alt+j"\n'
                         'type = "plugin_action"\ncommand = "someone.else.go"\n')
        assert run(tmp, other), "another plugin's binding counted as ours"

        # --- the opt-out file wins over everything ------------------------
        state = tmp / "state"
        state.mkdir()
        (state / "no-reminder").write_text("")
        assert run(tmp, stock, state) == [], "opt-out ignored"

        # --- a broken config is herdr's complaint to make, not ours -------
        broken = tmp / "broken.toml"
        broken.write_text("[keys\nthis is not toml")
        try:
            tomllib.loads(broken.read_text())
            raise AssertionError("fixture is valid TOML, so it tests nothing")
        except tomllib.TOMLDecodeError:
            pass
        assert run(tmp, broken) == [], "notified about a config we cannot read"

        # --- a config that does not exist yet -----------------------------
        assert run(tmp, tmp / "nope.toml"), "a missing config means nothing is bound"

    print("PASS: fires only when no keycaps binding exists, and never fails")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
