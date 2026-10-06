#!/usr/bin/env python3
"""Split paths: the addresses that decide which divider gets reset.

A wrong path moves the wrong divider, so the tree walk is checked directly.
The socket itself is not stubbed here - the real call is proved against a
live session instead, which a stub cannot do.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import even  # noqa: E402

PANE = {"type": "pane", "pane_id": "p"}
TREE = {"type": "split", "ratio": 0.55, "first": {
            "type": "split", "ratio": 0.75, "first": PANE, "second": PANE},
        "second": {
            "type": "split", "ratio": 0.2, "first": PANE,
            "second": {"type": "split", "ratio": 0.9,
                       "first": PANE, "second": PANE}}}


def main() -> int:
    paths = even.split_paths(TREE)
    # Root first, then first=False / second=True, depth first.
    assert paths == [[], [False], [True], [True, True]], paths

    # A single pane has no splits, and nothing to reset is not an error.
    assert even.split_paths(PANE) == []
    assert even.split_paths({}) == []

    # Every path must address a real split in the tree.
    for path in paths:
        node = TREE
        for step in path:
            node = node["second"] if step else node["first"]
        assert node["type"] == "split", (path, node)

    assert even.EVEN == 0.5

    print("PASS: split paths address every divider and nothing else")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
