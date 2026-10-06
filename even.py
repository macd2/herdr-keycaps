#!/usr/bin/env python3
"""Even out the panes in the current tab.

Herdr has no action, keybinding or CLI for this - `pane resize` only shifts a
split by a relative amount - but the socket API exposes
`layout.set_split_ratio`, so this walks the tab's split tree and sets every
ratio to half.

A split's address is the path taken to reach it: an empty list is the root,
then False descends into `first` and True into `second`.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

EVEN = 0.5


def socket_path() -> Path:
    override = os.environ.get("HERDR_SOCKET_PATH")
    if override:
        return Path(override)
    session = os.environ.get("HERDR_SESSION")
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "herdr"
    return base / "sessions" / session / "herdr.sock" if session else base / "herdr.sock"


def call(method: str, params: dict | None = None) -> dict:
    """One request, one response. The protocol is newline-delimited JSON."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(str(socket_path()))
        sock.sendall(
            (json.dumps({"id": "keycaps.even", "method": method,
                         "params": params or {}}) + "\n").encode()
        )
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
    reply = json.loads(buf.split(b"\n")[0] or b"{}")
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply["result"]


def split_paths(node: dict, path: tuple[bool, ...] = ()) -> list[list[bool]]:
    """Every split in the tree, as the path that addresses it."""
    if not isinstance(node, dict) or node.get("type") != "split":
        return []
    return ([list(path)]
            + split_paths(node.get("first", {}), (*path, False))
            + split_paths(node.get("second", {}), (*path, True)))


def main() -> int:
    try:
        layout = call("layout.export")["layout"]
        paths = split_paths(layout.get("root", {}))
        for path in paths:
            call("layout.set_split_ratio", {"path": path, "ratio": EVEN})
    except (OSError, RuntimeError, json.JSONDecodeError, KeyError) as error:
        print(f"could not even out the panes: {error}", file=sys.stderr)
        return 1
    # A tab with one pane has no splits; nothing to do is not a failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
