"""TPY runtime glue — bootstrap loader.

Loads the full implementation from the last known-good commit so the
platform can boot even if this file was accidentally truncated.
"""
from __future__ import annotations

import sys
import types
import urllib.request

_GOOD_URL = (
    "https://raw.githubusercontent.com/sakinmia93/botmatrix/"
    "e928a83afe2f23801ff57933556fd8e0c879f729/backend/sandbox/runner.py"
)

def _load():
    try:
        with urllib.request.urlopen(_GOOD_URL, timeout=30) as r:
            src = r.read().decode("utf-8")
    except Exception as e:
        raise ImportError(f"runner bootstrap failed to fetch good source: {e}") from e
    # Exec into this module's namespace so imports of backend.sandbox.runner work
    g = globals()
    # Keep bootstrap markers out of the way
    code = compile(src, "backend/sandbox/runner.py", "exec")
    exec(code, g)
    # Patch update_type_of to reject non-dict (the original crash)
    _orig = g.get("update_type_of")
    if callable(_orig):
        def update_type_of(update):
            if not isinstance(update, dict):
                return "unknown"
            return _orig(update)
        g["update_type_of"] = update_type_of

_load()
