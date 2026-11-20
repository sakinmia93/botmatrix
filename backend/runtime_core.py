"""Bot runtime core — bootstrap from known-good + TBC options scalar fix."""
from __future__ import annotations

import urllib.request

_GOOD = (
    "https://raw.githubusercontent.com/sakinmia93/botmatrix/"
    "62f8c22a8a2b1e5fef8ff45bf8e3e524c68b11c2/backend/runtime_core.py"
)

def _bootstrap():
    with urllib.request.urlopen(_GOOD, timeout=45) as r:
        src = r.read().decode("utf-8")

    # TBC parity: do NOT wrap scalar options into {options, value}.
    # match_command already returns the raw options value (e.g. "change_bal").
    # Wrapping broke `if options == "change_bal"` in user commands.
    src = src.replace(
        "opts = extra\n"
        "            if opts is not None and not isinstance(opts, dict):\n"
        "                opts = {\"options\": opts, \"value\": opts}\n"
        "            run_command(db, eb, acc, matched, update, secrets=secrets, options=opts)",
        "opts = extra  # keep scalar/dict as returned by match_command (TBC parity)\n"
        "            run_command(db, eb, acc, matched, update, secrets=secrets, options=opts)",
    )

    g = globals()
    exec(compile(src, __file__, "exec"), g)

_bootstrap()
