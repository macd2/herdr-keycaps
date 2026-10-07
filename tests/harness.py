#!/usr/bin/env python3
"""Shared test plumbing: an environment that cannot see the live herdr session.

Every test here drives a plugin script against a stub herdr, so the script must
resolve its pane and tab from the stub alone. Inside a herdr pane the session
exports HERDR_PANE_ID, HERDR_TAB_ID and friends, and a script that prefers
those over asking herdr then answers from the real session: the test goes green
outside herdr and red inside it, for reasons that have nothing to do with the
code under test.
"""

import os


def clean_env(**overrides) -> dict[str, str]:
    """The ambient environment minus every HERDR_* var, plus what a test sets.

    Dropping the whole prefix rather than a hand-kept list means a new session
    variable in herdr cannot quietly reach a script under test.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
    env.update(overrides)
    return env
