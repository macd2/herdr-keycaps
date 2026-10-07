#!/usr/bin/env python3
"""setup.py must add what is missing and touch nothing else.

The thing that makes this risky is that it edits a file the user wrote by hand.
So the cases that matter are not "did it add the keys" but: a config that has
none, a config that has all of them, a second run, a chord the user already
spent on something else, and the TOML ordering hazard where a new [keys] table
would land after an existing [[keys.command]] and stop the file parsing.
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

STOCK = 'onboarding = false\n\n[theme]\nname = "catppuccin"\n'


def run(cfg: Path, *args) -> tuple[int, str]:
    done = subprocess.run(
        [sys.executable, "setup.py", "--yes", *args], cwd=ROOT, timeout=30,
        capture_output=True, text=True,
        env=harness.clean_env(HERDR_CONFIG_PATH=str(cfg)),
    )
    return done.returncode, done.stdout + done.stderr


def wanted_counts() -> tuple[int, int]:
    keys, cmds = setup_mod.wanted()
    return len(keys), len(cmds)


def main() -> int:
    want_keys, want_cmds = wanted_counts()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # --- a config that does not exist yet -----------------------------
        fresh = tmp / "fresh" / "config.toml"
        code, out = run(fresh)
        assert code == 0, out
        assert fresh.exists(), "no config was created"
        parsed = tomllib.loads(fresh.read_text())
        assert len([k for k in parsed["keys"] if k != "command"]) == want_keys, parsed
        assert len(parsed["keys"]["command"]) == want_cmds, parsed

        # --- a stock config, then the same run again ----------------------
        cfg = tmp / "config.toml"
        cfg.write_text(STOCK)
        code, out = run(cfg)
        assert code == 0, out
        first = cfg.read_text()
        assert "catppuccin" in first, "the user's own settings were dropped"
        assert tomllib.loads(first)["theme"]["name"] == "catppuccin"

        code, out = run(cfg)
        assert code == 0, out
        assert "Nothing to do" in out, out
        assert cfg.read_text() == first, "a second run changed the file"

        # --- the ordering hazard: [[keys.command]] but no [keys] ----------
        # A [keys] table appended after it would redefine an existing table.
        hazard = tmp / "hazard.toml"
        hazard.write_text(STOCK + '\n[[keys.command]]\nkey = "alt+1"\n'
                          'type = "command"\ncommand = "echo hi"\n')
        code, out = run(hazard)
        assert code == 0, out
        text = hazard.read_text()
        tomllib.loads(text)  # the real assertion: it still parses
        assert text.index("[keys]\n") < text.index("[[keys.command]]"), text

        # --- chords the user already spent -------------------------------
        # alt+h on their own command, and their own zoom: both must survive.
        mine = tmp / "mine.toml"
        mine.write_text('[keys]\nzoom = ["alt+h"]\n\n# my note\n[[keys.command]]\n'
                        'key = "alt+m"\ntype = "command"\ncommand = "echo mine"\n')
        code, out = run(mine)
        assert code == 0, out
        after = tomllib.loads(mine.read_text())
        assert after["keys"]["zoom"] == ["alt+h"], after["keys"]["zoom"]
        assert "# my note" in mine.read_text(), "a comment was lost"
        bound = {b["command"]: b["key"] for b in after["keys"]["command"]}
        assert bound["echo mine"] == "alt+m", bound
        assert "macd2.keycaps.show" not in bound, "alt+h was stolen from zoom"
        assert "macd2.keycaps.move" not in bound, "alt+m was stolen"
        assert "macd2.keycaps.even" in bound, "unaffected bindings were skipped too"
        # Two chords this plugin wanted and cannot have, reported loudly;
        # their own zoom is simply a key they already set, so it is counted.
        assert out.count("  ! ") == 2, f"conflicts must be reported loudly:\n{out}"
        assert "alt+h is taken by zoom" in out, out
        assert "1 already in your config" in out, out

        # --- --only-plugin-keys leaves herdr's own actions alone ----------
        only = tmp / "only.toml"
        only.write_text(STOCK)
        code, out = run(only, "--only-plugin-keys")
        assert code == 0, out
        parsed = tomllib.loads(only.read_text())
        assert [k for k in parsed["keys"] if k != "command"] == [], parsed["keys"]
        assert len(parsed["keys"]["command"]) == want_cmds, parsed

        # --- --dry-run writes nothing ------------------------------------
        dry = tmp / "dry.toml"
        dry.write_text(STOCK)
        done = subprocess.run(
            [sys.executable, "setup.py", "--dry-run"], cwd=ROOT, timeout=30,
            capture_output=True, text=True,
            env=harness.clean_env(HERDR_CONFIG_PATH=str(dry)))
        assert done.returncode == 0, done.stderr
        assert dry.read_text() == STOCK, "--dry-run wrote to the config"

    print("PASS: adds what is missing, keeps what is there, repeats cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
