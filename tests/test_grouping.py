#!/usr/bin/env python3
"""Groups are ordered by use, and an unknown action is never dropped.

The grouping is a lookup with a fallback, so the fallback is the branch that
would silently swallow an action a future herdr release adds.
"""

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import keycaps  # noqa: E402

CONFIG = '''[keys]
focus_pane_left = ["prefix+h", "alt+left"]

[[keys.command]]
key = ["alt+h", "prefix+slash"]
type = "plugin_action"
command = "macd2.keycaps.show"
description = "Show all keybindings"
'''


def main() -> int:
    assert keycaps.group_for("focus_pane_left") == "Panes"
    assert keycaps.group_for("switch_tab") == "Tabs"
    assert keycaps.group_for("navigate_pane_up") == "Navigate mode"
    # The whole point of the fallback.
    assert keycaps.group_for("teleport_pane_to_mars") == "Other"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.toml"
        path.write_text(CONFIG)
        lines = keycaps.render(path)

    text = "\n".join(lines)
    assert "COMMANDS" in text, "custom commands section missing"
    assert text.index("COMMANDS") < text.index("PANES"), "custom commands not first"
    # Three columns: one-press chord, prefix form, description - in that order
    # on one line, each in its own column.
    assert re.search(r"alt\+h\s+ctrl\+b /\s+Show all keybindings", text), \
        "custom command not split into direct / prefix / description columns"
    # The override must win over herdr's default for that action.
    assert re.search(r"alt\+←\s+ctrl\+b h\s+Focus pane left", text), \
        "user override not applied, or columns out of order"
    assert "prefix+" not in text, "raw prefix+ notation leaked into the output"

    # group_for() returning "Other" is not enough; render() must also emit that
    # section, or a future herdr action would vanish between the two.
    real = keycaps.default_bindings
    keycaps.default_bindings = lambda: [
        ("prefix", ["ctrl+b"]),
        ("focus_pane_left", ["prefix+h"]),
        ("teleport_pane_to_mars", ["prefix+m"]),
    ]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(CONFIG)
            unknown = "\n".join(keycaps.render(path))
    finally:
        keycaps.default_bindings = real

    assert "OTHER" in unknown, "unknown action's section not rendered"
    assert "NAVIGATE MODE" not in unknown, "hidden section rendered anyway"
    assert "Resize mode" not in unknown, "hidden action rendered anyway"
    assert "Teleport pane to mars" in unknown, "unknown action dropped from output"

    # A four-arrow binding is one gesture; spelling it out four times would
    # widen the chord column for every other row.
    assert keycaps.collapse_arrows(
        ["ctrl+\u2191", "ctrl+\u2193", "ctrl+\u2192", "ctrl+\u2190"]) == ["ctrl+\u2191\u2193\u2192\u2190"]
    # Mixed modifiers, duplicates, or non-arrows must be left alone.
    assert keycaps.collapse_arrows(["ctrl+\u2191", "alt+\u2193"]) == ["ctrl+\u2191", "alt+\u2193"]
    assert keycaps.collapse_arrows(["ctrl+\u2191", "ctrl+\u2191"]) == ["ctrl+\u2191", "ctrl+\u2191"]
    assert keycaps.collapse_arrows(["ctrl+a", "ctrl+b"]) == ["ctrl+a", "ctrl+b"]
    assert keycaps.collapse_arrows(["\u2191", "\u2193"]) == ["\u2191", "\u2193"]
    assert keycaps.collapse_arrows(["alt+\u2191"]) == ["alt+\u2191"]

    # A command routed to a group must land inside it, once - an earlier
    # version appended a second PANES section at the bottom instead.
    routed_cfg = CONFIG + '''
[[keys.command]]
key = "alt+shift+enter"
type = "plugin_action"
command = "macd2.keycaps.even"
description = "Even out panes"
'''
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.toml"
        path.write_text(routed_cfg)
        text = "\n".join(keycaps.render(path))
    assert text.count("PANES") == 1, "routed command made a duplicate section"
    body = text.split("PANES", 1)[1]
    assert "Even out panes" in body, "routed command missing from its group"
    assert "Even out panes" not in text.split("PANES", 1)[0], "still under COMMANDS"

    print("PASS: groups ordered, custom first, unknown actions kept")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
