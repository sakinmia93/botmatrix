"""TPY runtime glue, routing, conversation state and update normalization."""
from __future__ import annotations

import urllib.request

_GOOD = (
    "https://raw.githubusercontent.com/sakinmia93/botmatrix/"
    "e928a83afe2f23801ff57933556fd8e0c879f729/backend/sandbox/runner.py"
)

# Injected immediately before run_sandboxed so critical names are never None.
_PRE_SANDBOX_GUARD = r'''
        # --- botmatrix guards ---
        from urllib.parse import quote as _uri_quote, unquote as _uri_unquote
        injected["encodeURIComponent"] = lambda s, _q=_uri_quote: _q(str(s if s is not None else ""), safe="~()*!.'\"")
        injected["decodeURIComponent"] = lambda s, _u=_uri_unquote: _u(str(s if s is not None else ""))
        if not callable(injected.get("handleNextCommand")):
            injected["handleNextCommand"] = bot_data_obj.handleNextCommand
        if not callable(injected.get("runCommand")):
            injected["runCommand"] = bot_data_obj.runCommand
        injected["run_command"] = injected.get("runCommand") or bot_data_obj.runCommand
        if injected.get("HTTP") is None or not hasattr(injected.get("HTTP"), "post"):
            from backend.sandbox.libs.http_lib import HTTPLib as _HTTPLib
            injected["HTTP"] = injected["http"] = _HTTPLib()
        else:
            injected["http"] = injected["HTTP"]
        if injected.get("User") is None:
            injected["User"] = UserObject(db, bot.id, int(uid_int or 0))
        if injected.get("bot") is None:
            injected["bot"] = bot_wrapper
        if injected.get("Bot") is None:
            injected["Bot"] = bot_data_obj
        if injected.get("Request") is None:
            from backend.sandbox.libs.request_lib import RequestModule as _RM2
            injected["Request"] = _RM2(bot.id, uid_int)
        # TBC: unwrap {options, value} so options == "change_bal" works
        _opt = injected.get("options")
        if isinstance(_opt, dict) and "options" in _opt and "json" not in _opt and "data" not in _opt and not _opt.get("__in_error_handler"):
            _inner = _opt.get("options")
            if isinstance(_inner, (str, int, float, bool)) or _inner is None:
                injected["options"] = _inner if _inner != "" else None
'''


def _bootstrap():
    with urllib.request.urlopen(_GOOD, timeout=45) as r:
        src = r.read().decode("utf-8")

    # handleNextCommand / runCommand always bound
    src = src.replace(
        'injected["handleNextCommand"] = getattr(bot_data_obj, "handleNextCommand", None) or getattr(bot_wrapper, "handleNextCommand")',
        'injected["handleNextCommand"] = bot_data_obj.handleNextCommand\n'
        '    injected["runCommand"] = bot_data_obj.runCommand\n'
        '    injected["run_command"] = bot_data_obj.runCommand',
        1,
    )

    needle = "result = run_sandboxed("
    if needle in src and "# --- botmatrix guards ---" not in src:
        src = src.replace(needle, _PRE_SANDBOX_GUARD + "\n        " + needle, 1)

    # Soften empty/unquoted .env (API_HASH hex without quotes, empty values)
    if "def _sanitize_env_source" not in src and "def _load_env_vars" in src:
        patch = '''
def _sanitize_env_source(src: str) -> str:
    import re as _re
    out = []
    for line in (src or "").splitlines():
        raw = line.rstrip()
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = _re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(.*)$", s)
        if not m:
            out.append(raw)
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == "":
            out.append(f"{key} = None")
            continue
        if val[0] in ("'\"", '"') or val in ("None", "True", "False") or val[0] in "([{":
            out.append(f"{key} = {val}")
            continue
        if _re.fullmatch(r"-?\\d+(\\.\\d+)?([eE][+-]?\\d+)?", val):
            out.append(f"{key} = {val}")
            continue
        out.append(f'{key} = "{val}"')
    return "\\n".join(out)

'''
        src = src.replace("def _load_env_vars", patch + "def _load_env_vars", 1)
        # call sanitize inside load if not present
        if "_sanitize_env_source(combined)" not in src:
            src = src.replace(
                "if not combined.strip():\n        return {}\n    code_hash",
                "if not combined.strip():\n        return {}\n    combined = _sanitize_env_source(combined)\n    if not combined.strip():\n        return {}\n    code_hash",
                1,
            )

    g: dict = {}
    exec(compile(src, "runner_remote.py", "exec"), g, g)

    globals().update({k: v for k, v in g.items() if not k.startswith("__")})

    _orig_match = g.get("match_command")
    _orig_run = g.get("run_command")

    if callable(_orig_match):
        def match_command(commands, update, db=None, bot_id=None, _o=_orig_match):
            cmd, extra = _o(commands, update, db=db, bot_id=bot_id)
            if cmd is not None:
                return cmd, extra
            try:
                msg = g['extract_message'](update) or {}
                text = (msg.get('text') or msg.get('caption') or '').strip()
            except Exception:
                return None, {}
            if not text.startswith('/'):
                return None, {}
            word = text.split()[0].split('@')[0]
            low = word.lower()
            if word in {'@', '~', '!', '*'}:
                return None, {}
            for c in commands or []:
                t = getattr(c, 'trigger', None)
                if t is None and isinstance(c, dict):
                    t = c.get('trigger')
                if t is None:
                    continue
                ts = str(t)
                if ts.lower() == low or ts.lower() == low.lstrip('/') or ('/' + ts.lstrip('/')).lower() == low:
                    return c, {}
            return None, {}
        g['match_command'] = match_command
        globals()['match_command'] = match_command

    if callable(_orig_run):
        def run_command(db, bot, account, command, update, secrets=None, options=None,
                        _skip_error_handler=False, capture=None, _o=_orig_run):
            if isinstance(command, dict):
                from types import SimpleNamespace
                command = SimpleNamespace(
                    trigger=command.get('trigger') or command.get('name') or '',
                    code=command.get('code') or '',
                    id=command.get('id'),
                    name=command.get('name') or command.get('trigger') or '',
                )
            if isinstance(options, dict) and 'options' in options and 'json' not in options and 'data' not in options and not options.get('__in_error_handler'):
                inner = options.get('options')
                if isinstance(inner, (str, int, float, bool)) or inner is None:
                    if options.get('params') is not None:
                        options = {'options': inner, 'params': options.get('params'), 'value': inner}
                    else:
                        options = inner
            return _o(
                db, bot, account, command, update,
                secrets=secrets, options=options,
                _skip_error_handler=_skip_error_handler, capture=capture,
            )
        g['run_command'] = run_command
        globals()['run_command'] = run_command

_bootstrap()
