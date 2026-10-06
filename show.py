#!/usr/bin/env python3
"""Open the Keycaps popup.

Keybindings can only target plugin actions, never plugin panes, so this action
is the shim between `type = "plugin_action"` and the `keys` pane. The
manifest already declares that pane as `placement = "popup"`, and the CLI's
--placement flag has no popup value, so the placement is deliberately left off
here and inherited from the manifest.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

PLUGIN = "macd2.keycaps"
ENTRYPOINT = "keys"


def main() -> int:
    herdr = os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr") or "herdr"
    try:
        result = subprocess.run(
            [herdr, "plugin", "pane", "open",
             "--plugin", PLUGIN, "--entrypoint", ENTRYPOINT],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"could not open Keycaps popup: {error}", file=sys.stderr)
        return 1

    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
