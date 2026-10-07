#!/usr/bin/env python3
"""The manifest must satisfy what the marketplace parses, and point at real files.

The herdr marketplace indexes a repository only when every manifest on the
default branch has parseable required metadata, so a typo here is an invisible
delisting rather than an error anyone sees.
"""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ("id", "name", "version", "min_herdr_version")
PLATFORMS = {"linux", "macos", "windows"}


def main() -> int:
    with (ROOT / "herdr-plugin.toml").open("rb") as fh:
        m = tomllib.load(fh)

    for key in REQUIRED:
        assert key in m and str(m[key]).strip(), f"required field missing: {key}"

    # Plugin ids: ASCII letters, digits, dot, colon, underscore, hyphen.
    assert all(c.isalnum() or c in ".:_-" for c in m["id"]), m["id"]
    # Entrypoint ids may not contain dots; herdr qualifies them as plugin.id.action.
    for kind in ("actions", "panes", "link_handlers"):
        ids = [e["id"] for e in m.get(kind, [])]
        assert len(ids) == len(set(ids)), f"duplicate {kind} id: {ids}"
        for i in ids:
            assert "." not in i, f"{kind} id may not contain a dot: {i}"

    assert set(m.get("platforms", [])) <= PLATFORMS, m.get("platforms")

    # Every command must name a file that exists, or the binding fails at press
    # time with nothing in the manifest to show why.
    for kind in ("actions", "panes", "startup", "build", "events", "link_handlers"):
        for entry in m.get(kind, []):
            argv = entry.get("command", [])
            scripts = [a for a in argv if a.endswith(".py")]
            for script in scripts:
                assert (ROOT / script).exists(), f"{kind} points at missing {script}"

    # The description is what the marketplace card shows; an empty one is a
    # blank card rather than an error.
    assert m.get("description", "").strip(), "description is what the card shows"

    print(f"PASS: manifest valid for the marketplace "
          f"({len(m.get('actions', []))} actions, {len(m.get('panes', []))} panes, "
          f"{len(m.get('startup', []))} startup)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
