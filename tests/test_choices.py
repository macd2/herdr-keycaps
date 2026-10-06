#!/usr/bin/env python3
"""Destination rows and argv: the two bits that decide where a pane lands.

Kept pure so they can be checked without a live session - a wrong tab id here
moves a real pane somewhere the user did not ask for.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import picker  # noqa: E402

SPACES = [
    ({"workspace_id": "w7", "label": "Redesign"}, [
        {"tab_id": "w7:t1", "label": "Claude1", "pane_count": 2},
        {"tab_id": "w7:t3", "label": "Hermes", "pane_count": 2},
    ]),
    ({"workspace_id": "w9", "label": "Infra"}, [
        {"tab_id": "w9:t1", "label": "Notes", "pane_count": 1},
    ]),
]


def main() -> int:
    rows = picker.build_rows(SPACES, "w7:t3")
    kinds = [r["kind"] for r in rows]

    # Each workspace heads its own group, with a 'new tab here' under it.
    assert kinds[0] == "heading" and rows[0]["label"] == "Redesign", rows[0]
    assert kinds[-1] == "new_workspace", kinds
    assert kinds.count("heading") == 2, kinds

    # The tab the pane already sits in is not offered; the other workspace's is.
    tabs = [r["tab_id"] for r in rows if r["kind"] == "tab"]
    assert tabs == ["w7:t1", "w9:t1"], tabs

    # Headings cannot be chosen, so numbering and the cursor skip them.
    picks = picker.selectable(rows)
    assert all(rows[i]["kind"] != "heading" for i in picks), picks
    assert len(picks) == len(rows) - 2, (len(picks), len(rows))

    # Pressing 1 must hit the first selectable row, not the first row.
    assert picker.move_args("w7:pA", rows[picks[0]]) == [
        "pane", "move", "w7:pA", "--tab", "w7:t1", "--split", "right"]

    # A tab in another workspace is reached by its tab id alone.
    other = next(r for r in rows if r.get("tab_id") == "w9:t1")
    assert picker.move_args("w7:pA", other) == [
        "pane", "move", "w7:pA", "--tab", "w9:t1", "--split", "right"]

    # 'new tab here' must carry the workspace it sat under, or it would land
    # in whichever workspace happens to be focused.
    new_tabs = [r for r in rows if r["kind"] == "new_tab"]
    assert [r["workspace_id"] for r in new_tabs] == ["w7", "w9"], new_tabs
    assert picker.move_args("w7:pA", new_tabs[1]) == [
        "pane", "move", "w7:pA", "--new-tab", "--workspace", "w9"]

    assert picker.move_args("w7:pA", rows[-1]) == [
        "pane", "move", "w7:pA", "--new-workspace"]

    print("PASS: rows grouped by workspace, argv targets the chosen one")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
