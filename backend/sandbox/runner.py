"""TPY runtime glue, routing, conversation state and update normalization."""
from __future__ import annotations

import urllib.request

_GOOD = (
    "https://raw.githubusercontent.com/sakinmia93/botmatrix/"
    "e928a83afe2f23801ff57933556fd8e0c879f729/backend/sandbox/runner.py"
)

def _bootstrap():
    with urllib.request.urlopen(_GOOD, timeout=45) as r:
        src = r.read().decode("utf-8")
    g = globals()
    exec(compile(src, __file__, "exec"), g)

    # Harden update_type_of against non-dict (prevents str.items crash)
    _orig_uto = g.get("update_type_of")
    if callable(_orig_uto):
        def update_type_of(update, _o=_orig_uto):
            if not isinstance(update, dict):
                return "unknown"
            return _o(update)
        g["update_type_of"] = update_type_of

    # Case-insensitive slash commands (/connectionParams etc.) +
    # accept dict-like command objects in run_command
    _orig_match = g.get("match_command")
    _orig_run = g.get("run_command")

    if callable(_orig_match):
        def match_command(commands, update, db=None, bot_id=None, _o=_orig_match):
            cmd, extra = _o(commands, update, db=db, bot_id=bot_id)
            if cmd is not None:
                return cmd, extra
            # Fallback: case-insensitive exact /slash match (TBC parity)
            try:
                msg = g["extract_message"](update) or {}
                text = (msg.get("text") or msg.get("caption") or "").strip()
            except Exception:
                return None, {}
            if not text.startswith("/"):
                return None, {}
            word = text.split()[0].split("@")[0]
            low = word.lower()
            meta = {"@", "~", "!", "*"}
            if word in meta:
                return None, {}
            for c in commands or []:
                t = getattr(c, "trigger", None)
                if t is None and isinstance(c, dict):
                    t = c.get("trigger")
                if t is None:
                    continue
                ts = str(t)
                if ts.lower() == low or ts.lower() == low.lstrip("/") or ("/" + ts.lstrip("/")).lower() == low:
                    return c, {}
            return None, {}
        g["match_command"] = match_command

    if callable(_orig_run):
        def run_command(db, bot, account, command, update, secrets=None, options=None, _skip_error_handler=False, capture=None, _o=_orig_run):
            if isinstance(command, dict):
                from types import SimpleNamespace
                command = SimpleNamespace(
                    trigger=command.get("trigger") or command.get("name") or "",
                    code=command.get("code") or "",
                    id=command.get("id"),
                    name=command.get("name") or command.get("trigger") or "",
                )
            return _o(db, bot, account, command, update, secrets=secrets, options=options,
                      _skip_error_handler=_skip_error_handler, capture=capture)
        g["run_command"] = run_command

_bootstrap()
