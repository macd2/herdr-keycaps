#!/usr/bin/env python3
"""uninstall.py must take out this plugin's bindings and nothing else.

The dangerous direction here is over-removal: this edits a file whose other
contents are the user's whole herdr setup. So the case that proves it is a round
trip - stock config, setup.py, uninstall.py - which has to give back the original
byte for byte. Anything that survives one and not the other shows up as a diff.

The [keys] layer is deliberately not "our stuff": it binds herdr's own actions,
which keep working once the plugin is gone.
"""

import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import harness

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import setup as setup_mod  # noqa: E402

STOCK = ('onboarding = false\n\n[theme]\nname = "catppuccin"\n\n'
         '[ui]\npane_borders = "always"\n')


def run(script: str, cfg: Path, *args) -> str:
    done = subprocess.run(
        [sys.executable, script, "--yes", *args], cwd=ROOT, timeout=30,
        capture_output=True, text=True,
        env=harness.clean_env(HERDR_CONFIG_PATH=str(cfg)))
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout + done.stderr


def keycaps_bindings(cfg: Path) -> list[str]:
    data = tomllib.loads(cfg.read_text())
    return [b["command"] for b in data.get("keys", {}).get("command", [])
            if str(b.get("command", "")).startswith("macd2.keycaps.")]


def main() -> int:
    want_keys, want_cmds = setup_mod.wanted()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # --- the round trip, byte for byte -------------------------------
        trip = tmp / "trip.toml"
        trip.write_text(STOCK)
        run("setup.py", trip)
        assert trip.read_text() != STOCK, "setup.py wrote nothing to undo"
        run("uninstall.py", trip, "--also-direct-layer")
        assert trip.read_text() == STOCK, (
            f"round trip did not restore the original:\n{trip.read_text()!r}")

        # --- the default keeps herdr's own layer --------------------------
        keep = tmp / "keep.toml"
        keep.write_text(STOCK)
        run("setup.py", keep)
        run("uninstall.py", keep)
        data = tomllib.loads(keep.read_text())
        assert keycaps_bindings(keep) == [], keycaps_bindings(keep)
        assert len([k for k in data["keys"] if k != "command"]) == len(want_keys)
        assert data["theme"]["name"] == "catppuccin", "the user's settings went"

        # --- a hand-written config: other plugins, comments, own keys -----
        mixed = tmp / "mixed.toml"
        mixed.write_text(
            '# my own notes\n[keys]\nzoom = ["alt+z"]\n\n'
            '# someone else\'s plugin\n[[keys.command]]\nkey = "alt+p"\n'
            'type = "plugin_action"\ncommand = "other.plugin.go"\n\n'
            '[[keys.command]]\nkey = "alt+h"\ntype = "plugin_action"\n'
            'command = "macd2.keycaps.show"\n')
        run("uninstall.py", mixed, "--also-direct-layer")
        text = mixed.read_text()
        data = tomllib.loads(text)
        assert "# my own notes" in text and "someone else" in text, text
        assert data["keys"]["zoom"] == ["alt+z"], "their zoom was removed"
        assert [b["command"] for b in data["keys"]["command"]] == ["other.plugin.go"], data
        assert keycaps_bindings(mixed) == []

        # --- ours, then a comment, then someone else's block --------------
        # The comment introduces the block below it, so removing ours must not
        # take it: the span has to stop at the comment, not at the next header.
        order = tmp / "order.toml"
        order.write_text(
            '[[keys.command]]\nkey = "alt+h"\ntype = "plugin_action"\n'
            'command = "macd2.keycaps.show"\n\n'
            '# this note belongs to the block below\n'
            '[[keys.command]]\nkey = "alt+p"\ntype = "plugin_action"\n'
            'command = "other.plugin.go"\n')
        run("uninstall.py", order)
        text = order.read_text()
        assert "this note belongs to the block below" in text, text
        assert [b["command"] for b in tomllib.loads(text)["keys"]["command"]] == \
            ["other.plugin.go"], text

        # --- a value retuned since setup stays even with --also ----------
        retuned = tmp / "retuned.toml"
        retuned.write_text(STOCK)
        run("setup.py", retuned)
        # setup.py pads names to the widest it wrote, so match the line, not a
        # guess at its spacing.
        body, swapped = re.subn(r'^zoom(\s*)= .*$', r'zoom\1= ["alt+0"]',
                                retuned.read_text(), count=1, flags=re.M)
        assert swapped == 1, "fixture did not retune anything"
        retuned.write_text(body)
        out = run("uninstall.py", retuned, "--also-direct-layer")
        assert tomllib.loads(retuned.read_text())["keys"]["zoom"] == ["alt+0"], out
        assert "zoom kept: you changed it since" in out, out

        # --- nothing of ours present --------------------------------------
        none = tmp / "none.toml"
        none.write_text(STOCK)
        out = run("uninstall.py", none, "--also-direct-layer")
        assert "Nothing to do" in out, out
        assert none.read_text() == STOCK, "touched a config with none of ours"

        # --- --dry-run writes nothing -------------------------------------
        dry = tmp / "dry.toml"
        dry.write_text(STOCK)
        run("setup.py", dry)
        before = dry.read_text()
        done = subprocess.run(
            [sys.executable, "uninstall.py", "--dry-run", "--also-direct-layer"],
            cwd=ROOT, timeout=30, capture_output=True, text=True,
            env=harness.clean_env(HERDR_CONFIG_PATH=str(dry)))
        assert done.returncode == 0, done.stderr
        assert dry.read_text() == before, "--dry-run wrote to the config"
        assert len(want_cmds) == 7, f"bindings.toml changed shape: {len(want_cmds)}"

    print("PASS: removes only this plugin's bindings, and the round trip is exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
