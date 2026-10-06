#!/usr/bin/env python3
"""Open the move-pane picker.

Keybindings can only target plugin actions, never plugin panes, so this action
is the shim between type = "plugin_action" and the `picker` pane. Placement
comes from the manifest, since the CLI's --placement has no popup value.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

PLUGIN = "macd2.keycaps"
ENTRYPOINT = "picker"


def main() -> int:
    herdr = os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr") or "herdr"
    try:
        result = subprocess.run(
            [herdr, "plugin", "pane", "open",
             "--plugin", PLUGIN, "--entrypoint", ENTRYPOINT],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"could not open the pane picker: {error}", file=sys.stderr)
        return 1

    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
