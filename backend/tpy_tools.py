"""Code-editor language service: live catalog, validation and dry-run test, all from the real engine."""
from __future__ import annotations

import ast
import builtins
import inspect
import re
import time
from typing import Dict, List

from backend import appdb, runtime
from backend.errors import ApiError
from backend.sandbox.safe_builtins import FORBIDDEN_AST_NAMES, SAFE_BUILTIN_NAMES, FORBIDDEN_ATTR_NAMES, _format_string_is_safe

_cache: dict = {}


def _sig(fn) -> str:
    try:
        s = str(inspect.signature(fn))
        s = s.replace("(self, ", "(").replace("(self)", "()")
        return s
    except Exception:
        return "(...)"


def _doc(obj) -> str:
    d = inspect.getdoc(obj) or ""
    d = d.strip().split("\n\n")[0][:400]
    return re.sub(r"\b(TBC|TPY|Telebot Creator|Telebot)\b[- ]?(compatible|style|identical|convention)?", "", d).replace("  ", " ").replace("( ", "(")


def _members(cls) -> List[dict]:
    out = []
    for name in dir(cls):
        if name.startswith("_"):
            continue
        try:
            attr = inspect.getattr_static(cls, name)
        except Exception:
            continue
        if isinstance(attr, property):
            out.append({"name": name, "kind": "property", "signature": "", "doc": _doc(attr)})
        elif callable(attr) or isinstance(attr, (staticmethod, classmethod)):
            fn = attr.__func__ if isinstance(attr, (staticmethod, classmethod)) else attr
            out.append({"name": name, "kind": "method", "signature": _sig(fn), "doc": _doc(fn)})
    return out


def catalog() -> dict:
    if _cache:
        return _cache
    from backend.sandbox import context_objects as co
    from backend.sandbox import libs_namespace as ln
    from backend.telegram.bot_wrapper import BotWrapper

    objs: Dict[str, List[dict]] = {}
    classes = {
        "bot": BotWrapper, "Bot": co.BotDataObject, "User": co.UserObject, "Account": co.AccountObject,
        "message": co.MessageObject, "call": co.CallbackQueryObject,
    }
    for k, cls in classes.items():
        objs[k] = _members(cls)
    # message/msg/call expose instance attributes (text, chat, from_user ...) and fall back to any
    # raw Telegram field at runtime, so suggest all real ones rather than only class-level methods.
    try:
        _m = co.MessageObject({})
        _extra = [k for k in vars(_m) if not k.startswith("_")] + [
            "entities", "caption_entities", "audio", "animation", "video_note", "venue", "poll", "dice",
            "new_chat_members", "left_chat_member", "pinned_message", "web_app_data", "message_thread_id",
            "forward_date", "forward_origin", "via_bot", "sender_chat", "edit_date", "media_group_id",
            "has_media_spoiler", "successful_payment", "reply_to_message", "quote", "link_preview_options",
            "business_connection_id", "users_shared", "chat_shared", "contact", "game", "invoice"]
        _have = {m["name"] for m in objs["message"]}
        for k in dict.fromkeys(_extra):
            if k not in _have:
                objs["message"].append({"name": k, "kind": "property", "signature": "", "doc": "Message field."})
    except Exception:
        pass
    objs["msg"] = objs["message"]
    # libs.* — introspect a real instance so every attribute is exactly what user code sees
    lib_attrs = []
    try:
        import tempfile
        inst = ln.LibsNamespace(None, 0, 0, tempfile.gettempdir(), {})
        for attr in sorted(vars(inst)):
            if attr.startswith("_"):
                continue
            val = getattr(inst, attr)
            kind = "object"
            lib_attrs.append({"name": attr, "kind": kind, "signature": "", "doc": _doc(type(val))})
            objs[f"libs.{attr}"] = _members(type(val))
    except Exception:
        pass
    objs["libs"] = lib_attrs
    # Telegram Bot API methods are resolved dynamically by bot.<method>(...)
    import json as _json, os as _os
    try:
        _sf = _json.load(open(_os.path.join(_os.path.dirname(__file__), "v15_surface.json")))
    except Exception:
        _sf = {"telegram_camel": [], "telegram_snake": []}
    tg_methods = list(_sf["telegram_camel"]) + ["sendPoll", "sendChatAction", "getMe", "getFile", "setMyCommands"]
    tg_methods = list(dict.fromkeys(tg_methods))
    # Only the documented surface is suggested in the editor
    allow = _sf.get("allow", {})
    for k in ("Bot", "Account", "User"):
        if allow.get(k):
            objs[k] = [m for m in objs[k] if m["name"] in allow[k] or m["name"].lower() in {a.lower() for a in allow[k]}]
    keep = _sf.get("libs")
    if keep:
        low = {n.lower(): n for n in keep}
        seen_l = set()
        flt = []
        for l in objs["libs"]:
            nm = l["name"]
            if nm in keep or (nm.lower() in low and nm == low[nm.lower()]):
                flt.append(l)
        objs["libs"] = flt
        for key in [k for k in list(objs) if k.startswith("libs.")]:
            lname = key[5:]
            if lname not in {l["name"] for l in flt}:
                objs.pop(key, None)
    objs["msg"] = objs["message"]
    have = {m["name"] for m in objs["bot"]}
    for n in tg_methods + list(_sf.get("telegram_snake") or []):
        if n not in have:
            have.add(n)
            objs["bot"].append({"name": n, "kind": "method", "signature": "(**params)", "doc": f"Telegram Bot API: {n}."})
    # Capital `Bot` is used interchangeably with `bot` in TBC/TBS scripts (Bot.sendMessage, Bot.getChatId, …).
    # After the allow-list filter, merge every bot/Telegram method onto Bot so the editor stops false warnings.
    extra_bot = [
        "getChatId", "get_chat_id", "getDefaultChatId", "sendMessage", "sendPhoto", "sendDocument",
        "sendVideo", "sendAudio", "sendVoice", "sendAnimation", "sendSticker", "sendLocation",
        "sendContact", "sendPoll", "sendChatAction", "editMessageText", "editMessageCaption",
        "editMessageReplyMarkup", "deleteMessage", "answerCallbackQuery", "getMe", "getFile",
        "getFileUrl", "replyText", "replyMessage", "replyPhoto", "setWebhook", "deleteWebhook",
        "handleNextCommand", "runCommand", "runCommandAfter", "saveData", "getData", "deleteData",
    ]
    have_B = {m["name"] for m in objs.get("Bot", [])}
    for m in objs.get("bot", []):
        if m["name"] not in have_B:
            objs.setdefault("Bot", []).append(dict(m))
            have_B.add(m["name"])
    for n in extra_bot + tg_methods + list(_sf.get("telegram_snake") or []):
        if n not in have_B:
            objs.setdefault("Bot", []).append({"name": n, "kind": "method", "signature": "(**params)", "doc": f"Bot API helper: {n}."})
            have_B.add(n)
    objs["call"] = [{"name": n, "kind": "property", "signature": "", "doc": ""} for n in
                    ("id", "data", "message", "from_user", "chat_id", "message_id", "answer")]

    globs = [
        {"name": "bot", "kind": "object", "doc": "Send messages and call the Telegram Bot API.", "signature": ""},
        {"name": "Bot", "kind": "object", "doc": "Bot-wide data, commands and settings.", "signature": ""},
        {"name": "User", "kind": "object", "doc": "Data saved for the current user.", "signature": ""},
        {"name": "Account", "kind": "object", "doc": "Your account: points, bots and transfers.", "signature": ""},
        {"name": "message", "kind": "object", "doc": "The incoming message.", "signature": ""},
        {"name": "msg", "kind": "object", "doc": "Short form of message.", "signature": ""},
        {"name": "call", "kind": "object", "doc": "The pressed inline button (callback query).", "signature": ""},
        {"name": "libs", "kind": "module", "doc": "Built-in libraries.", "signature": ""},
        {"name": "params", "kind": "constant", "doc": "Text after the command.", "signature": ""},
        {"name": "options", "kind": "constant", "doc": "Options passed to this command.", "signature": ""},
        {"name": "user", "kind": "constant", "doc": "Telegram id of the current user.", "signature": ""},
        {"name": "chat_id", "kind": "constant", "doc": "Id of the current chat.", "signature": ""},
        {"name": "ReturnCommand", "kind": "constant", "doc": "raise ReturnCommand to stop this command.", "signature": ""},
        {"name": "InlineKeyboardMarkup", "kind": "function", "doc": "Inline keyboard.", "signature": "(...)"},
        {"name": "InlineKeyboardButton", "kind": "function", "doc": "Inline keyboard button.", "signature": "(...)"},
        {"name": "ReplyKeyboardMarkup", "kind": "function", "doc": "Reply keyboard.", "signature": "(...)"},
        {"name": "ReplyKeyboardRemove", "kind": "function", "doc": "Remove reply keyboard.", "signature": "(...)"},
        {"name": "ForceReply", "kind": "function", "doc": "Force a reply.", "signature": "(...)"},
        {"name": "json", "kind": "module", "doc": "JSON helpers.", "signature": ""},
        {"name": "re", "kind": "module", "doc": "Regular expressions.", "signature": ""},
        {"name": "hashlib", "kind": "module", "doc": "Hashing.", "signature": ""},
        {"name": "HTTP", "kind": "object", "doc": "HTTP requests.", "signature": ""},
        {"name": "Api", "kind": "object", "doc": "Set the result returned to a webhook / API caller.", "signature": ""},
        {"name": "CSV", "kind": "object", "doc": "CSV helper.", "signature": ""},
        {"name": "web3_", "kind": "object", "doc": "Web3 library.", "signature": ""},
        {"name": "TBC_Web3_", "kind": "object", "doc": "Web3 library (alias).", "signature": ""},
        {"name": "Request", "kind": "object", "doc": "Request helper.", "signature": ""},
        {"name": "MembershipCheck", "kind": "function", "doc": "Check channel / group membership.", "signature": "(...)"},
        {"name": "LinkPreviewOptions", "kind": "function", "doc": "Link preview options.", "signature": "(...)"},
        {"name": "callback_data", "kind": "constant", "doc": "Data of the pressed inline button.", "signature": ""},
        {"name": "update", "kind": "object", "doc": "The raw update.", "signature": ""},
        {"name": "update_type", "kind": "constant", "doc": "Type of the incoming update.", "signature": ""},
        {"name": "bot_id", "kind": "constant", "doc": "Id of this bot.", "signature": ""},
        {"name": "bot_token", "kind": "constant", "doc": "Token of this bot.", "signature": ""},
        {"name": "u", "kind": "constant", "doc": "Telegram id of the current user.", "signature": ""},
        {"name": "user_id", "kind": "constant", "doc": "Telegram id of the current user.", "signature": ""},
        {"name": "command", "kind": "constant", "doc": "Name of the running command.", "signature": ""},
        {"name": "left_points", "kind": "constant", "doc": "Points left on the account.", "signature": ""},
        {"name": "webhook_payload", "kind": "constant", "doc": "Payload of the webhook call.", "signature": ""},
        {"name": "returnCommand", "kind": "function", "doc": "Stop this command.", "signature": "()"},
        {"name": "returncommand", "kind": "constant", "doc": "raise returncommand to stop this command.", "signature": ""},
        {"name": "base64", "kind": "module", "doc": "Base64 helpers.", "signature": ""},
        {"name": "binascii", "kind": "module", "doc": "Binary/ASCII helpers.", "signature": ""},
        {"name": "regex", "kind": "module", "doc": "Regular expressions.", "signature": ""},
        {"name": "md5", "kind": "function", "doc": "MD5 hash.", "signature": "(text)"},
        {"name": "time", "kind": "module", "doc": "Time helpers.", "signature": ""},
        {"name": "sleep", "kind": "function", "doc": "Wait some seconds.", "signature": "(seconds)"},
        {"name": "bunchify", "kind": "function", "doc": "Dict to attribute access.", "signature": "(obj)"},
        {"name": "encodejson", "kind": "function", "doc": "Object to JSON text.", "signature": "(obj)"},
        {"name": "jsondumps", "kind": "function", "doc": "Object to JSON text.", "signature": "(obj)"},
        {"name": "bf_json", "kind": "function", "doc": "Pretty JSON.", "signature": "(obj)"},
        {"name": "parse_qs", "kind": "function", "doc": "Parse a query string.", "signature": "(qs)"},
        {"name": "rawurlencode", "kind": "function", "doc": "URL-encode text.", "signature": "(text)"},
        {"name": "encodeURIComponent", "kind": "function", "doc": "URL-encode text.", "signature": "(text)"},
        {"name": "decodeURIComponent", "kind": "function", "doc": "URL-decode text.", "signature": "(text)"},
        {"name": "isNumeric", "kind": "function", "doc": "Is this value a number?", "signature": "(value)"},
        {"name": "is_numeric", "kind": "function", "doc": "Is this value a number?", "signature": "(value)"},
    ]
    seen_g = set()
    globs = [g for g in globs if not (g["name"] in seen_g or seen_g.add(g["name"]))]
    for n in SAFE_BUILTIN_NAMES:
        if hasattr(builtins, n):
            globs.append({"name": n, "kind": "function" if callable(getattr(builtins, n)) else "constant", "doc": "", "signature": ""})
    _cache.update({
        "globals": globs, "objects": objs,
        "keywords": ["if", "elif", "else", "for", "while", "in", "not", "and", "or", "def", "lambda", "try", "except",
                     "finally", "raise", "pass", "break", "continue", "True", "False", "None", "with", "as", "is", "del"],
        "forbidden": sorted(FORBIDDEN_AST_NAMES),
        "modules": ["json", "re", "math", "datetime", "hashlib", "uuid", "base64", "random", "statistics", "collections", "itertools", "functools"],
    })
    return _cache


# ------------------------------------------------------------------ validation
def validate(code: str, name: str = "") -> dict:
    errors: List[dict] = []
    code = code or ""
    if len(code) > 400_000:
        return {"ok": False, "errors": [{"line": 1, "col": 1, "message": "Code is too long.", "severity": "error"}]}
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        errors.append({"line": e.lineno or 1, "col": (e.offset or 1), "endCol": (e.end_offset or (e.offset or 1) + 1),
                       "message": (e.msg or "Syntax error").capitalize(), "severity": "error"})
        return {"ok": False, "errors": errors}
    cat = catalog()
    # Names the user's own code defines (msg = ..., def f(msg), for msg in ..., except E as msg) are theirs, not the engine's:
    # `msg.text` on a variable you assigned yourself must not be checked against a built-in object of the same name.
    mine = set()
    for nd in ast.walk(tree):
        if isinstance(nd, ast.Name) and isinstance(nd.ctx, (ast.Store, ast.Del)):
            mine.add(nd.id)
        elif isinstance(nd, ast.arg):
            mine.add(nd.arg)
        elif isinstance(nd, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            mine.add(nd.name)
        elif isinstance(nd, ast.ExceptHandler) and nd.name:
            mine.add(nd.name)
    objs = {k: v for k, v in cat["objects"].items() if k not in mine}
    in_func = [0]

    def add(node, msg, sev="error"):
        errors.append({"line": getattr(node, "lineno", 1), "col": getattr(node, "col_offset", 0) + 1,
                       "endCol": getattr(node, "end_col_offset", None) and getattr(node, "end_col_offset") + 1,
                       "message": msg, "severity": sev})

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, n):
            in_func[0] += 1
            self.generic_visit(n)
            in_func[0] -= 1
        visit_AsyncFunctionDef = visit_FunctionDef
        visit_Lambda = visit_FunctionDef

        def visit_Return(self, n):
            if not in_func[0]:
                add(n, "`return` isn't allowed at the top level. Use `raise ReturnCommand` to stop the command.")
            self.generic_visit(n)

        def visit_Import(self, n):
            from backend.sandbox.safe_builtins import import_allowed, SAFE_IMPORTS
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""]
            if getattr(n, "level", 0) or not all(import_allowed(m) for m in mods):
                add(n, "That import isn't allowed. You can import: " + ", ".join(SAFE_IMPORTS) + ".")

        visit_ImportFrom = visit_Import

        def visit_Name(self, n):
            if n.id in FORBIDDEN_AST_NAMES:
                add(n, f"`{n.id}` is not allowed.")

        def visit_Constant(self, n):
            if isinstance(n.value, str) and not _format_string_is_safe(n.value):
                add(n, "A format field may not use `.` or `[` (attribute/item access is not allowed).")

        def visit_Attribute(self, n):
            if n.attr.startswith("_") or n.attr in FORBIDDEN_ATTR_NAMES:
                add(n, f"Private attribute `{n.attr}` is not allowed.")
            base = _dotted(n.value)
            if base in objs and base not in ("bot", "call", "message", "msg") and isinstance(n.ctx, ast.Load):
                known = {m["name"] for m in objs[base]}
                if known and n.attr not in known and base not in ("libs",):
                    add(n, f"`{base}` has no function or property called `{n.attr}`.", "warning")
                elif base == "libs" and n.attr not in known and n.attr not in ("Polygon", "ARB", "TTcoin", "Tomochain"):
                    add(n, f"There is no library called `libs.{n.attr}`.", "warning")
            self.generic_visit(n)

    V().visit(tree)
    ok = not any(e["severity"] == "error" for e in errors)
    return {"ok": ok, "errors": errors}


def _dotted(n) -> str:
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "libs":
        return f"libs.{n.attr}"
    return ""


# ------------------------------------------------------------------ dry run
def test_command(user_id: str, bot_id: str, body: dict) -> dict:
    from backend import models as em
    from backend.database import SessionLocal
    from backend.sandbox.runner import run_command
    with appdb.read() as c:
        b = appdb.one(c, "SELECT * FROM bots WHERE id=? AND user_id=?", (bot_id, user_id))
        u = appdb.one(c, "SELECT telegram_chat_id FROM users WHERE id=?", (user_id,))
    if not b:
        raise ApiError("Bot not found", 404)
    name = str(body.get("name") or "").strip()
    code = body.get("code")
    if code is None:
        for cm in appdb.jload(b["commands_json"], []):
            if cm.get("name") == name:
                code = cm.get("code") or ""
    if code is None:
        raise ApiError("Command not found", 404)
    v = validate(code, name)
    if not v["ok"]:
        e = next(x for x in v["errors"] if x["severity"] == "error")
        return {"ok": False, "error": f"Line {e['line']}: {e['message']}", "aborted": False, "durationMs": 0, "calls": [], "logs": []}
    pk = runtime.sync_bot(bot_id)
    if pk is None:
        raise ApiError("Could not prepare the bot for testing.", 500)
    text = str(body.get("text") if body.get("text") is not None else (name if name.startswith("/") else ""))[:4000]
    uid = int(u["telegram_chat_id"]) if u and u["telegram_chat_id"] and str(u["telegram_chat_id"]).isdigit() else 1
    cb = body.get("callbackData")
    update_type = str(body.get("update_type") or body.get("updateType") or "").strip() or None
    user = {"id": uid, "is_bot": False, "first_name": "Tester", "language_code": "en"}
    chat = {"id": uid, "type": "private", "first_name": "Tester"}
    msg = {"message_id": 1, "date": int(time.time()), "chat": chat, "from": user, "text": text if text else None}
    # Build update matching real Telegram + TBC shape (update_type injected by runner)
    if cb or update_type == "callback_query":
        update = {"update_id": 1, "callback_query": {
            "id": "1", "from": user, "data": str(cb or text or "btn"),
            "message": {**msg, "text": msg.get("text") or "None"}, "chat_instance": "1",
        }}
    elif update_type == "pre_checkout_query":
        update = {"update_id": 1, "pre_checkout_query": {
            "id": "7151627186281124860", "from": user, "currency": body.get("currency") or "XTR",
            "total_amount": int(body.get("total_amount") or 1),
            "invoice_payload": str(body.get("invoice_payload") or text or "payload"),
        }}
    elif update_type == "inline_query":
        update = {"update_id": 1, "inline_query": {
            "id": "1", "from": user, "query": text or "", "offset": "",
        }}
    elif update_type == "shipping_query":
        update = {"update_id": 1, "shipping_query": {
            "id": "1", "from": user, "invoice_payload": text or "payload",
            "shipping_address": {"country_code": "BD", "state": "", "city": "Dhaka", "street_line1": "", "street_line2": "", "post_code": ""},
        }}
    elif update_type and update_type not in ("message", "edited_message"):
        # Generic special update: put payload under the update_type key
        payload = body.get("payload") if isinstance(body.get("payload"), dict) else {"from": user}
        if "from" not in payload:
            payload = {**payload, "from": user}
        update = {"update_id": 1, update_type: payload}
    else:
        update = {"update_id": 1, "message": msg}
    db = SessionLocal()
    try:
        eb = db.query(em.Bot).filter_by(id=pk).first()
        acc = db.query(em.Account).filter_by(id=eb.owner_id).first()
        cmd = em.Command(bot_id=eb.id, trigger=name or "/test", trigger_type="command", code=code)
        capture: list = []
        t0 = time.time()
        res = run_command(db, eb, acc, cmd, update, secrets={}, options={"value": (text.split(" ", 1) + [""])[1]} if text else None, capture=capture)
        db.rollback()
        return {"ok": bool(res.get("ok")), "error": res.get("error"), "aborted": bool(res.get("aborted")),
                "durationMs": int((time.time() - t0) * 1000), "calls": capture, "logs": []}
    finally:
        db.close()


# ------------------------------------------------------------------ formatter
import ast as _ast
import io as _io
import keyword as _kw
import tokenize as _tk

_BINOPS = {"+", "-", "*", "/", "//", "%", "**", "@", "==", "!=", "<", ">", "<=", ">=", "=", "+=", "-=", "*=", "/=", "//=", "%=",
           "**=", "@=", "&", "|", "^", "<<", ">>", "&=", "|=", "^=", ">>=", "<<=", "->", ":="}
_WORDS = {"and", "or", "not", "in", "is", "if", "else", "elif", "for", "while", "return", "yield", "lambda", "import", "from",
          "as", "with", "assert", "del", "raise", "await", "async", "except", "global", "nonlocal"}


def _line_tokens_ok(toks) -> bool:
    for t in toks:
        if t.type in (getattr(_tk, "FSTRING_START", -1), getattr(_tk, "FSTRING_MIDDLE", -1), getattr(_tk, "FSTRING_END", -1)):
            return False
        if t.type == _tk.STRING and t.start[0] != t.end[0]:
            return False
        if t.type == _tk.COMMENT and False:
            return False
    return len({t.start[0] for t in toks if t.type not in (_tk.NL, _tk.NEWLINE)} | {t.end[0] for t in toks if t.type not in (_tk.NL, _tk.NEWLINE)}) == 1


def _respace(toks) -> str:
    """Rebuild one single-line logical line with clean spacing (strings and comments are kept as written)."""
    out, depth, prev = [], [], None   # depth stack holds '(' '[' '{'
    kw_paren = []                      # parallel to depth: True when '(' is a call/def bracket
    for t in toks:
        s = t.string
        if t.type in (_tk.NEWLINE, _tk.NL, _tk.ENDMARKER, _tk.INDENT, _tk.DEDENT):
            continue
        if t.type == _tk.COMMENT:
            out.append(("  " if out else "") + s)
            prev = t
            continue
        sp = ""
        if prev is not None:
            ps = prev.string
            unary = False
            if s in ("-", "+", "~") or (s in ("*", "**") and depth):
                unary = prev.type == _tk.OP and ps not in (")", "]", "}") or (prev.type == _tk.NAME and ps in _WORDS) \
                    or (s in ("*", "**") and prev.type == _tk.OP and ps in ("(", ",", "[", "{"))
            if s == "=" and depth and depth[-1] == "(":
                sp = ""
            elif ps == "=" and depth and depth[-1] == "(" and prev.type == _tk.OP:
                sp = ""
            elif s in (",", ")", "]", "}", ";") or (s == ":" and not (depth and depth[-1] == "{" and False)):
                sp = ""
            elif ps in ("(", "[", "{") or ps in (".", "~") and prev.type == _tk.OP:
                sp = ""
            elif s in ("(", "[") and (prev.type in (_tk.NAME, _tk.STRING) and ps not in _WORDS or ps in (")", "]", "}")):
                sp = ""
            elif s == ".":
                sp = ""
            elif ps in ("*", "**") and prev.type == _tk.OP and getattr(prev, "_unary", False):
                sp = ""
            elif ps in ("-", "+", "~") and getattr(prev, "_unary", False):
                sp = ""
            elif s in _BINOPS and not unary:
                sp = " "
            elif ps in _BINOPS and not getattr(prev, "_unary", False):
                sp = " "
            elif ps == ",":
                sp = " "
            elif ps == ":" and prev.type == _tk.OP:
                sp = "" if (depth and depth[-1] == "[") else " "
            else:
                sp = " "
            if unary:
                t = _tk.TokenInfo(t.type, t.string, t.start, t.end, t.line)
                try:
                    object.__setattr__(t, "_unary", True)
                except Exception:
                    pass
        out.append(sp + s)
        if s in ("(", "[", "{"):
            depth.append(s)
        elif s in (")", "]", "}") and depth:
            depth.pop()
        prev = t
    return "".join(out)



def format_code(code: str) -> dict:
    """Clean, consistent formatting: 4-space indentation from the real block structure, tidy spacing, max two blank
    lines. The result is checked to be the exact same program; if not, only whitespace is normalised."""
    src = (code or "").replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    try:
        tree_before = _ast.dump(_ast.parse(src))
    except SyntaxError as e:
        return {"ok": False, "error": f"Line {e.lineno}: {e.msg}"}
    toks = list(_tk.generate_tokens(_io.StringIO(src + ("" if src.endswith("\n") else "\n")).readline))
    lines_out, cur, level, blank = [], [], 0, 0

    def flush():
        nonlocal cur, blank
        if not cur:
            return
        first = next((t for t in cur if t.type not in (_tk.NL, _tk.INDENT, _tk.DEDENT)), None)
        body = [t for t in cur if t.type not in (_tk.NL,)]
        if first is None:
            cur = []
            return
        multi = {t.start[0] for t in cur if t.type not in (_tk.NEWLINE, _tk.NL, _tk.INDENT, _tk.DEDENT)} | \
                {t.end[0] for t in cur if t.type not in (_tk.NEWLINE, _tk.NL, _tk.INDENT, _tk.DEDENT)}
        real = [t for t in cur if t.type not in (_tk.NEWLINE, _tk.NL, _tk.INDENT, _tk.DEDENT)]
        if real and len(multi) == 1 and _line_tokens_ok(real):
            text = _respace(real)
        else:
            a, b = real[0].start, real[-1].end
            seg = src.split("\n")
            if a[0] == b[0]:
                text = seg[a[0] - 1][a[1]:b[1]]
            else:
                text = "\n".join([seg[a[0] - 1][a[1]:]] + seg[a[0]:b[0] - 1] + [seg[b[0] - 1][:b[1]]])
        pad = "    " * level
        head, _, rest = text.partition("\n")
        lines_out.append(pad + head + (("\n" + rest) if rest else ""))
        cur = []

    pending_blank = 0
    for t in toks:
        if t.type == _tk.INDENT:
            level += 1
            continue
        if t.type == _tk.DEDENT:
            level = max(0, level - 1)
            continue
        if t.type == _tk.NL and not cur:
            pending_blank += 1
            continue
        if t.type == _tk.COMMENT and not cur:
            # stand-alone comment line
            for _ in range(min(pending_blank, 2)):
                lines_out.append("")
            pending_blank = 0
            lines_out.append("    " * level + t.string.rstrip())
            continue
        if not cur and t.type not in (_tk.ENDMARKER, _tk.NEWLINE):
            for _ in range(min(pending_blank, 2)):
                lines_out.append("")
            pending_blank = 0
        if t.type == _tk.ENDMARKER:
            break
        cur.append(t)
        if t.type == _tk.NEWLINE:
            flush()
    flush()
    out = "\n".join(lines_out).rstrip("\n") + "\n" if lines_out else ""
    try:
        if _ast.dump(_ast.parse(out)) != tree_before:
            raise ValueError("changed")
    except Exception:
        # fall back: whitespace-only clean-up
        out = "\n".join(l.rstrip() for l in src.split("\n")).strip("\n") + "\n"
    return {"ok": True, "code": out, "changed": out != (code or "")}
