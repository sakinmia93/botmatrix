"""TPY runtime glue, routing, conversation state and update normalization."""
import hashlib
import traceback
from typing import Optional
from sqlalchemy.orm import Session
from backend import models
from backend.config import STORAGE_DIR, MAX_EXEC_SECONDS
from backend.telegram.bot_wrapper import BotWrapper
from backend.sandbox.executor import run_sandboxed, SandboxError
from backend.sandbox.context_objects import (UserObject, BotDataObject, AccountObject,
    MessageObject, CallbackQueryObject, ApiObject, ReturnCommand)
from backend.sandbox.libs_namespace import LibsNamespace
from backend.sandbox.safe_builtins import build_preimported_modules
from backend.sandbox.telegram_types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply,
    LinkPreviewOptions, MsgFacade,
)


# TBC: max 3 Bot.runCommand hops per top-level user update (thread-local)
import threading as _threading
_CHAIN = _threading.local()

def _chain_begin():
    """Reset chain depth at the start of a top-level webhook/command run."""
    _CHAIN.depth = 0

def _chain_enter():
    d = getattr(_CHAIN, "depth", 0)
    if d >= 3:
        return False
    _CHAIN.depth = d + 1
    return True

def _chain_depth():
    return getattr(_CHAIN, "depth", 0)

_RESERVED_INJECTED_NAMES = {"handleNextCommand","CheckMembership","dir","Admin","JSON","URL","Hash","bot","Bot","message","msg","call","user","u","User","Account","Api",
    "params","options","libs","update","update_type","webhook_payload","__builtins__","__name__",
    "ReturnCommand","returnCommand","__doc__","__loader__","__spec__","__package__"}
_ENV_CACHE = {}

def _raise_return_command(*_a, **_k):
    raise ReturnCommand()


def apply_html_entities(text):
    """TBC apply_html_entities — escape text for Telegram HTML parse_mode."""
    if text is None:
        return ""
    s = str(text)
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )

class _MemberResult(dict):
    """Per-channel results ({channel: bool}); truthy only when the user is in ALL channels."""
    def __bool__(self):
        return bool(self) and all(self.values()) if len(self) else False
    __nonzero__ = __bool__


def MembershipCheck(channels=None, u=None, bot_token=None):
    """MembershipCheck(channel_or_list, user_id) / CheckMembership(...).

    One channel -> True/False. A list -> a result that is truthy only if the user joined every channel (it also keeps the
    per-channel dict). A wrong channel name or a bot that is not an admin of the channel raises an error."""
    channels = channels or []
    single = isinstance(channels, str)
    if single:
        channels = [channels]
    token = bot_token
    if not token:
        try:
            import builtins as _bi
            token = getattr(_bi, "_TBC_BOT_TOKEN", None)
        except Exception:
            token = None
    if not token:
        raise RuntimeError("MembershipCheck: no bot context")
    from backend.telegram.bot_wrapper import BotWrapper
    bw = BotWrapper(token)
    results = _MemberResult()
    if isinstance(u, str) and u.strip().lstrip("-").isdigit():
        u = int(u.strip())
    if not isinstance(u, int) or isinstance(u, bool):
        raise RuntimeError("MembershipCheck needs the Telegram user id (a number), e.g. MembershipCheck(['@mychannel'], u). Got: " + repr(u)[:40])
    clean = []
    for ch in channels:
        c = str(ch).strip().strip("'\"[] ,")        # tolerate quotes/brackets pasted into the name
        if c and not c.startswith("@") and not c.lstrip("-").isdigit() and "t.me/" not in c:
            c = "@" + c
        c = c.replace("https://t.me/", "@").replace("http://t.me/", "@").replace("t.me/", "@") if "t.me/" in c else c
        if c:
            clean.append(c)
    channels = clean
    for ch in channels:
        try:
            m = bw.getChatMember(chat_id=int(ch) if str(ch).lstrip("-").isdigit() else ch, user_id=u)
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            if "user not found" in low or "participant_id_invalid" in low:
                results[str(ch)] = False
                continue
            raise RuntimeError(f"MembershipCheck failed for {ch}: {msg} (check the channel name and make the bot an admin there)")
        status = m.get("status") if isinstance(m, dict) else getattr(m, "status", None)
        results[str(ch)] = status in ("member", "administrator", "creator") or (status == "restricted" and bool(m.get("is_member", True) if isinstance(m, dict) else True))
    if single:
        return bool(next(iter(results.values()), False))
    return results


CheckMembership = MembershipCheck


def parse_qs(data_in_str):
    from urllib.parse import parse_qs as _pq
    return {k: v[0] if len(v) == 1 else v for k, v in _pq(str(data_in_str)).items()}

def rawurlencode(url):
    from urllib.parse import quote
    return quote(str(url), safe="")

def encodeURIComponent(url):
    from urllib.parse import quote
    return quote(str(url), safe="~()*!.'")

def decodeURIComponent(url):
    from urllib.parse import unquote
    return unquote(str(url))


def _bunchify(obj):
    """Convert dict/list to attribute-accessible objects (TBC bunchify)."""
    from backend.sandbox.context_objects import _AttrDict
    if isinstance(obj, dict):
        return _AttrDict({k: _bunchify(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_bunchify(v) for v in obj]
    return obj

def _is_numeric(value):
    try:
        float(value)
        return True
    except Exception:
        return False

def _encodejson(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)

def _bf_json(value):
    import json
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value

def _md5(value):
    import hashlib
    return hashlib.md5(str(value).encode()).hexdigest()



# Official Telegram Bot API Update fields (core.telegram.org/bots/api#update)
# At most ONE of these optional fields is present per update (besides update_id).
KNOWN_UPDATE_TYPES = [
    "message", "edited_message", "channel_post", "edited_channel_post",
    "business_connection", "business_message", "edited_business_message", "deleted_business_messages",
    "guest_message",
    "message_reaction", "message_reaction_count",
    "inline_query", "chosen_inline_result", "callback_query",
    "shipping_query", "pre_checkout_query", "purchased_paid_media",
    "poll", "poll_answer",
    "my_chat_member", "chat_member", "chat_join_request",
    "chat_boost", "removed_chat_boost",
    "managed_bot", "subscription", "stopped_message_generation",
]


def update_type_of(update: dict) -> str:
    """Telegram's update type = the one key besides update_id. Known types first; any NEW type Telegram adds later is picked up automatically."""
    for k in KNOWN_UPDATE_TYPES:
        if k in update:
            return k
    for k, v in (update or {}).items():
        if k != "update_id" and isinstance(v, (dict, list)) and not k.startswith("_"):
            return k
    return "unknown"


def normalize_tbc_update(update: dict) -> dict:
    """Return the TPY-facing update using TBC's documented `from_user` schema.

    The transport layer keeps the raw Telegram update untouched; only the object
    injected as `update` into TPY commands is normalized.
    """
    import copy
    data = copy.deepcopy(update or {})
    known = list(KNOWN_UPDATE_TYPES)

    def rename_from(obj):
        if isinstance(obj, dict):
            if "from" in obj and "from_user" not in obj:
                obj["from_user"] = obj.pop("from")
            elif "from" in obj:
                obj.pop("from", None)
            return obj
        return obj

    for key in list(data.keys()):
        if key != "update_id" and isinstance(data.get(key), dict):
            rename_from(data[key])

    # Documented callback normalization: expose `call`, mirror its message as
    # `message`, and provide a safe text fallback on the callback message.
    cq = data.get("callback_query")
    if isinstance(cq, dict):
        data["call"] = cq
        cq_message = cq.get("message")
        if isinstance(cq_message, dict):
            rename_from(cq_message)
            cq_message["text"] = "None"
            data["message"] = cq_message
            data["message"]["update_type"] = "callback_query"
        elif "message" not in data:
            data["message"] = {"text": "None", "update_type": "callback_query"}
        data["update_type"] = "callback_query"
    else:
        typ = update_type_of(data)
        if isinstance(data.get("message"), dict):
            data["message"].setdefault("update_type", typ)
        elif typ != "unknown" and isinstance(data.get(typ), dict):
            obj = data[typ]
            obj.setdefault("update_type", typ)
            data["message"] = obj

    # The normalized top-level event always advertises its update type.
    data["update_type"] = "callback_query" if "callback_query" in data else update_type_of(data)
    return data


def extract_message(update: dict) -> dict:
    """Build the TPY-facing `message` dict for any Telegram update type.

    TBC always exposes a `message` object with:
      - update_type  (e.g. message / pre_checkout_query / my_chat_member)
      - text         ("None" when the update has no text — never empty string)
      - from / from_user
    so `bot.sendMessage(message)` and `message.update_type` work in every handler.
    """
    typ = update_type_of(update)

    def _stamp(obj: dict, ut: str) -> dict:
        if not isinstance(obj, dict):
            obj = {}
        else:
            obj = dict(obj)  # shallow copy — never mutate the live update
        obj["update_type"] = ut
        # TBC: missing text becomes the literal string used by `if msg == "None"`
        if obj.get("text") in (None, ""):
            if obj.get("caption") not in (None, ""):
                pass  # caption handled by MessageObject
            else:
                obj.setdefault("text", None)  # MessageObject/_TBCOptionalStr → "None"
        # from_user alias (TBC schema)
        if "from" in obj and "from_user" not in obj:
            obj["from_user"] = obj["from"]
        elif "from_user" in obj and "from" not in obj:
            obj["from"] = obj["from_user"]
        return obj

    if "message" in update:
        return _stamp(update.get("message") or {}, "message" if typ == "message" else typ)
    if "edited_message" in update:
        return _stamp(update.get("edited_message") or {}, "edited_message")
    if "channel_post" in update:
        return _stamp(update.get("channel_post") or {}, "channel_post")
    if "edited_channel_post" in update:
        return _stamp(update.get("edited_channel_post") or {}, "edited_channel_post")
    if "callback_query" in update:
        cq = update["callback_query"] or {}
        msg = dict(cq.get("message") or {})
        src = cq.get("from_user") or cq.get("from") or msg.get("from") or msg.get("from_user") or {}
        msg["from"] = src
        msg["from_user"] = src
        msg["_callback_data"] = cq.get("data")
        msg["_callback_query_id"] = cq.get("id")
        msg["id"] = cq.get("id")
        msg["data"] = cq.get("data")
        return _stamp(msg, "callback_query")

    if typ != "unknown":
        obj = update.get(typ)
        if typ == "inline_query" and isinstance(obj, dict):
            return _stamp({
                "from": obj.get("from") or obj.get("from_user") or {},
                "from_user": obj.get("from") or obj.get("from_user") or {},
                "text": obj.get("query"),
                "id": obj.get("id"),
                "query": obj.get("query"),
                "offset": obj.get("offset"),
                "chat_type": obj.get("chat_type"),
            }, "inline_query")
        if isinstance(obj, dict):
            obj = dict(obj)
            # Ensure chat_id context for private-query updates (pre_checkout, shipping, ...)
            if "chat" not in obj:
                u = obj.get("user") or obj.get("from") or obj.get("from_user") or {}
                if isinstance(u, dict) and u.get("id") is not None:
                    obj["chat"] = {"id": u["id"], "type": "private"}
                    if "from" not in obj and "from_user" not in obj:
                        obj["from"] = u
            return _stamp(obj, typ)
    return _stamp({}, typ if typ != "unknown" else "message")



def _params_value(value):
    """TBC params: missing → None-like (falsy, == None), but .split() safe.
    Always coerce to str so `"x" + params` and params never introduce int concat errors.
    """
    from backend.sandbox.context_objects import _TBCOptionalStr
    if value is None or value == "":
        return _TBCOptionalStr(None)
    if isinstance(value, _TBCOptionalStr):
        return value
    return _TBCOptionalStr(str(value))

def extract_params(update: dict, trigger: str):
    """TBC-compatible: return None when there are no params (not empty string)."""
    msg = extract_message(update)
    if update_type_of(update) == "callback_query":
        data = (msg.get("_callback_data") or "").strip()
        if not data:
            return None
        if trigger and data == trigger:
            return None
        if trigger and data.startswith(trigger + " "):
            rest = data[len(trigger):].strip()
            return rest if rest else None
        # callback_data is the full payload when it does not target this trigger as prefix
        return data
    text = (msg.get("text") or msg.get("caption") or "").strip()
    if not text:
        return None
    if trigger and trigger.startswith("/") and text.startswith(trigger):
        rest = text[len(trigger):].strip()
        # strip @botusername if present on the command word only; params after space
        if rest.startswith("@"):
            # "/start@BotName args" → after removing trigger "/start", rest is "@BotName args"
            parts = rest.split(None, 1)
            rest = parts[1].strip() if len(parts) > 1 else ""
        return rest if rest else None
    # For non-slash triggers (text/any/*) the whole text is params
    return text


def _load_env_vars(db, bot, base_injected):
    # Load all env-type commands (".env", "~", trigger_type=env) into shared globals
    env_cmds = db.query(models.Command).filter(
        models.Command.bot_id == bot.id,
        (models.Command.trigger_type == "env") | (models.Command.trigger.in_(["~", ".env"]))
    ).all()
    env_cmds = [c for c in env_cmds if c.trigger != "~"]       # `~` is a preface prepended to every command, not an env loader
    if not env_cmds:
        return {}
    combined = "\n".join(c.code for c in env_cmds if c.code and c.code.strip())
    if not combined.strip():
        return {}
    code_hash = hashlib.sha256(combined.encode()).hexdigest()
    cached = _ENV_CACHE.get(bot.id)
    if cached and cached[0] == code_hash:
        return cached[1]
    env_globals = dict(base_injected)
    try:
        result_globals = run_sandboxed(combined, env_globals, timeout_seconds=MAX_EXEC_SECONDS)
    except Exception as first_err:
        # One bad line must not lose every variable: run statement by statement.
        import ast as _ast
        result_globals = dict(env_globals)
        failures = []
        try:
            tree = _ast.parse(combined)
            stmts = [(_ast.get_source_segment(combined, n) or "", n.lineno) for n in tree.body]
        except SyntaxError:
            stmts = []
            failures.append(f"syntax error: {first_err}")
        for src, ln in stmts:
            if not src.strip():
                continue
            try:
                result_globals = run_sandboxed(src, result_globals, timeout_seconds=MAX_EXEC_SECONDS)
            except Exception as e:
                failures.append(f"line {ln}: {e}")
        if failures:
            try:
                from backend import models as _m
                db.add(_m.ErrorLog(bot_id=bot.id, command_trigger="~",
                                   message="~ env load failed: " + "; ".join(failures[:5]), traceback=""))
                db.commit()
            except Exception:
                pass
    pre = set()
    resolved = {
        k: v for k, v in result_globals.items()
        if k not in _RESERVED_INJECTED_NAMES and k not in pre and not k.startswith("__")
    }
    _ENV_CACHE[bot.id] = (code_hash, resolved)
    return resolved


def invalidate_env_cache(bot_id): _ENV_CACHE.pop(bot_id, None)


def _make_translate_hook(db, bot, update):
    """Auto-Translate: only active when the bot has the switch ON."""
    if not getattr(bot, "auto_translate", False):
        return None
    try:
        from backend.translation import make_hook
        return make_hook(db, bot, update)
    except Exception:
        return None


def run_command(db, bot, account, command, update, secrets=None, options=None, _skip_error_handler=False, capture=None):
    secrets = secrets or {}
    raw_msg = extract_message(update)
    # Resolve user/chat from every common Telegram update shape
    telegram_user_id = (raw_msg.get("from") or {}).get("id")
    if telegram_user_id is None:
        telegram_user_id = ((update.get("message") or {}).get("from") or {}).get("id")
    if telegram_user_id is None:
        telegram_user_id = ((update.get("callback_query") or {}).get("from") or {}).get("id")
    if telegram_user_id is None and update_type_of(update) == "inline_query":
        telegram_user_id = ((update.get("inline_query") or {}).get("from") or {}).get("id")
    try:
        if telegram_user_id is not None:
            telegram_user_id = int(telegram_user_id)
    except Exception:
        pass

    # Always stamp the real Telegram update type onto the message object so
    # message.update_type matches TBC (pre_checkout_query, my_chat_member, ...),
    # even if extract_message forgot a field.
    _ut = update_type_of(update)
    if isinstance(raw_msg, dict):
        raw_msg = dict(raw_msg)
        raw_msg["update_type"] = _ut if _ut != "unknown" else raw_msg.get("update_type") or "message"
        if "from" in raw_msg and "from_user" not in raw_msg:
            raw_msg["from_user"] = raw_msg["from"]
    message_obj = MessageObject(raw_msg)
    # Hard-set so __str__/attribute never fall back to "message"
    message_obj.update_type = raw_msg.get("update_type") or _ut or "message"
    call_raw = update.get("callback_query") or {}
    call_obj = CallbackQueryObject(call_raw) if "callback_query" in update else None

    default_chat = message_obj.chat_id
    if default_chat in (None, 0, "0", ""):
        default_chat = (raw_msg.get("chat") or {}).get("id")
    if default_chat in (None, 0, "0", ""):
        default_chat = ((update.get("message") or {}).get("chat") or {}).get("id")
    if default_chat in (None, 0, "0", "") and telegram_user_id is not None:
        default_chat = telegram_user_id
    try:
        if default_chat not in (None, ""):
            default_chat = int(default_chat)
    except Exception:
        pass
    default_msg_id = message_obj.message_id
    default_cq_id = call_raw.get("id") if call_raw else None

    bot_wrapper = BotWrapper(
        bot.token,
        default_chat_id=default_chat,
        default_message_id=default_msg_id,
        default_callback_query_id=default_cq_id,
        capture=capture,
        pre_hook=_make_translate_hook(db, bot, update),
    )
    user_obj = UserObject(db, bot.id, int(telegram_user_id)) if telegram_user_id is not None else None
    # Detect error-handler context from options marker (set by _run_error_handler)
    _in_err = False
    if isinstance(options, dict) and options.get("__in_error_handler"):
        _in_err = True
    runtime = {
        "db": db,
        "bot": bot,
        "account": account,
        "update": update,
        "user_id": telegram_user_id,
        "current_trigger": getattr(command, "trigger", None),
        "in_error_handler": _in_err or (getattr(command, "trigger", None) == "!"),
    }
    bot_data_obj = BotDataObject(db, bot.id, owner_account=account, runtime=runtime)
    libs = LibsNamespace(db, bot.id, telegram_user_id, STORAGE_DIR, secrets)
    from backend.sandbox.libs.request_lib import RequestModule
    Request = RequestModule(bot.id, telegram_user_id)
    Lib = libs  # TBS-style Lib.Random, Lib.RefLib, ...

    # TBC globals aliases
    CSV = libs.CSV
    web3_ = getattr(libs, "web3lib", None)
    result_container = {}

    # Normalize options so webhook handlers can use options.json / options.data
    # TBC allows scalar options: Bot.handleNextCommand("/start", options="check_captcha")
    # so `if options == "check_captcha"` must work.
    from backend.sandbox.context_objects import _AttrDict
    # Always define raw_options so injected["command"] never hits UnboundLocalError.
    raw_options = {}
    if options is None:
        options_obj = None
    elif isinstance(options, (str, int, float, bool)):
        options_obj = options if options != "" else None
        if options_obj is not None:
            raw_options = {"value": options_obj}
    else:
        raw_options = dict(options) if isinstance(options, dict) else {"value": options}
        if "json" not in raw_options and update.get("webhook_payload") is not None:
            raw_options["json"] = update.get("webhook_payload")
        if "data" not in raw_options and update.get("webhook_payload") is not None:
            raw_options["data"] = update.get("webhook_payload")
        options_obj = _AttrDict(raw_options) if raw_options else None
        if raw_options.get("__in_error_handler"):
            from backend.sandbox.context_objects import _ErrOptions
            options_obj = _ErrOptions(str(raw_options.get("error") or raw_options.get("value") or ""), raw_options)

    from backend.sandbox import tbs_compat as _tbs
    # Attach Bot.info to bot wrapper for bot.info() calls
    bot_wrapper.info = bot_data_obj.info
    bot_wrapper.token = bot.token
    bot_wrapper.username = bot.username
    bot_wrapper.id = bot.id

    try:
        uid_int = int(telegram_user_id) if telegram_user_id is not None else None
    except Exception:
        uid_int = telegram_user_id
    try:
        chat_int = int(default_chat) if default_chat not in (None, "") else uid_int
    except Exception:
        chat_int = default_chat if default_chat is not None else uid_int
    if chat_int not in (None, 0, "0"):
        bot_wrapper._default_chat_id = chat_int

    tpy_update = normalize_tbc_update(update)

    injected = {
        "bot": bot_wrapper, "Bot": bot_data_obj, "message": message_obj, "msg": MsgFacade(message_obj),
        "call": call_obj,
        "user": uid_int, "u": uid_int, "user_id": uid_int, "chat_id": chat_int,
        "User": user_obj,
        "Account": AccountObject(db, account), "Api": ApiObject(result_container),
        "params": _params_value(
            (options.get("params") if isinstance(options, dict) and options.get("params") is not None
             else extract_params(update, command.trigger))
        ), "options": (
            options_obj.get("options") if isinstance(options_obj, dict) and "options" in options_obj and "params" in options_obj
            else options_obj
        ),
        # TBC `!` error handler: the failed command trigger is available as `command`.
        "command": (raw_options.get("command") if isinstance(raw_options, dict) and raw_options.get("command") else command.trigger),
        "error": options_obj.get("error") if isinstance(options_obj, dict) else None,
        "update": tpy_update, "update_type": update_type_of(update),
        "webhook_payload": update.get("webhook_payload"), "ReturnCommand": ReturnCommand,
        "returnCommand": _raise_return_command,
        # Telegram helper classes used by many exported TBC bots
        "InlineKeyboardMarkup": InlineKeyboardMarkup,
        "InlineKeyboardButton": InlineKeyboardButton,
        "ReplyKeyboardMarkup": ReplyKeyboardMarkup,
        "ReplyKeyboardRemove": ReplyKeyboardRemove,
        "ForceReply": ForceReply,
        "MembershipCheck": MembershipCheck, "CheckMembership": MembershipCheck,
        "parse_qs": parse_qs,
        "rawurlencode": rawurlencode,
        "encodeURIComponent": encodeURIComponent,
        "decodeURIComponent": decodeURIComponent,
        "returncommand": ReturnCommand,
        "left_points": getattr(account, "points", 0),
        "binascii": __import__("binascii"),
        "regex": __import__("re"),

        "LinkPreviewOptions": LinkPreviewOptions,
        # TBC globals helpers
        "apply_html_entities": apply_html_entities, "bunchify": _bunchify,
        "isNumeric": _is_numeric,
        "encodejson": _encodejson,
        "jsondumps": _encodejson,
        "bf_json": _bf_json,
        "md5": _md5,
        "base64": __import__("base64"),
        "binascii": __import__("binascii"),
        "hashlib": __import__("hashlib"),
        "re": __import__("re"),
        # CSV/web3_ filled after libs init
        "is_numeric": _is_numeric,

        "JSON": _tbs.JSONNS(), "URL": _tbs.URLNS(), "Hash": _tbs.HashNS(), "Admin": _tbs.AdminObject(db, bot.id, uid_int),
        "libs": libs, "CSV": CSV, "web3_": web3_, "Lib": Lib, "Request": Request,
        # Global HTTP (TBC docs: use HTTP.get / HTTP.post without libs.)
        "HTTP": libs.HTTP,
        "http": libs.HTTP,
        "bot_id": str(getattr(bot, "public_id", None) or bot.id),
        "bot_token": bot.token,
    }

    # Safe json.dumps for OptionalStr / _TBCNum inside user code.
    # IMPORTANT: keep a reference to the *original* dumps — assigning back onto
    # the module and calling module.dumps would recurse forever.
    import json as _json_mod
    from backend.sandbox.context_objects import _json_default as _jd
    _orig_dumps = _json_mod.dumps
    def _dumps_safe(*a, **k):
        k.setdefault("default", _jd)
        return _orig_dumps(*a, **k)
    class _JsonNS:
        """Thin namespace: dumps is safe; everything else proxies to stdlib json."""
        dumps = staticmethod(_dumps_safe)
        loads = staticmethod(_json_mod.loads)
        load = staticmethod(_json_mod.load)
        dump = staticmethod(_json_mod.dump)
        JSONDecodeError = _json_mod.JSONDecodeError
        JSONEncoder = _json_mod.JSONEncoder
        JSONDecoder = _json_mod.JSONDecoder
    injected["json"] = _JsonNS()

    # TBC convenience: time.sleep / sleep available without import
    import time as _time_mod
    from backend.sandbox.safe_builtins import _limited_sleep

    class _TimeNS:
        """Docs: `time` is available without import and `time.sleep()` is capped at 10 seconds."""
        sleep = staticmethod(_limited_sleep)

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            return getattr(_time_mod, name)
    injected["time"] = _TimeNS()
    injected["sleep"] = _limited_sleep

    injected["Api"]._tg = bot_wrapper
    try:
        libs.RefLib._params = str(injected["params"]) if injected.get("params") not in (None, "None") else None
    except Exception:
        pass
    injected.update(_load_env_vars(db, bot, injected))
    # Env (~) must never clobber live Telegram / TBC context
    injected["u"] = uid_int
    injected["user"] = uid_int
    injected["user_id"] = uid_int
    injected["chat_id"] = chat_int
    injected["bot"] = bot_wrapper
    injected["Bot"] = bot_data_obj
    # docs (command-in-tpy) also show the bare form: handleNextCommand("name")
    injected["handleNextCommand"] = getattr(bot_data_obj, "handleNextCommand", None) or getattr(bot_wrapper, "handleNextCommand")
    injected["message"] = message_obj
    injected["msg"] = MsgFacade(message_obj)  # msg.strip() / int(msg) / msg.text
    injected["User"] = user_obj
    injected["libs"] = libs
    injected["Lib"] = libs
    from backend.sandbox.libs.request_lib import RequestModule as _RM
    injected["Request"] = _RM(bot.id, uid_int)
    injected["CSV"] = getattr(libs, "CSV", None)
    injected["web3_"] = getattr(libs, "web3lib", None)
    injected["TBC_Web3_"] = getattr(libs, "TBC_Web3_", getattr(libs, "web3lib", None))
    injected["HTTP"] = getattr(libs, "HTTP", None)
    injected["http"] = getattr(libs, "HTTP", None)
    injected["ReturnCommand"] = ReturnCommand
    injected["returnCommand"] = _raise_return_command
    injected["returncommand"] = ReturnCommand
    injected["call"] = call_obj
    injected["callback_data"] = getattr(call_obj, "data", None) if call_obj is not None else None
    if chat_int not in (None, 0, "0"):
        bot_wrapper._default_chat_id = chat_int
    try:
        # If this run was triggered by a pending handleNextCommand wait, consume
        # the state NOW (before user code). User code may call handleNextCommand
        # again to re-arm; that must not be wiped after the sandbox returns.
        if user_obj and user_obj.get_state() == command.trigger:
            user_obj.clear_state()

        code_to_run, preface_lines = command.code, 0
        if getattr(command, "trigger", None) not in ("~", ".env"):
            _pre = db.query(models.Command).filter_by(bot_id=bot.id, trigger="~").first()
            if _pre is not None and (_pre.code or "").strip():
                _p = _pre.code.rstrip("\n") + "\n"
                code_to_run, preface_lines = _p + (command.code or ""), _p.count("\n")
        _tok = bot.token
        def _is_uid(v):
            return (isinstance(v, int) and not isinstance(v, bool) and v > 0) or (isinstance(v, str) and v.isdigit())
        def _membership(channels=None, u=None, bot_token=None):
            if _is_uid(channels) and u is not None and not _is_uid(u):      # docs also show CheckMembership(user_id, channel)
                channels, u = u, channels
            elif channels is not None and u is None and _is_uid(channels):
                channels, u = None, channels
            return MembershipCheck(channels, u if (u is not None and u != "") else uid_int, bot_token or _tok)
        injected["MembershipCheck"] = injected["CheckMembership"] = _membership
        def _dir(*a):
            if not a:                     # TBS: `'NAME' not in dir()` tells whether an environment variable exists
                return sorted(k for k in injected if not str(k).startswith("_"))
            return sorted(n for n in dir(a[0]) if not n.startswith("_"))
        injected["dir"] = _dir
        run_sandboxed(code_to_run, injected, timeout_seconds=MAX_EXEC_SECONDS)
        return {"ok":True,"error":None,"aborted":False,"webhook_result":result_container.get("result")}
    except ReturnCommand:
        # raise ReturnCommand() / raise returnCommand() means "stop this command"
        # For @ preprocessor the webhook treats aborted=True as "do not run main command".
        return {"ok":True,"error":None,"aborted":True,"webhook_result":result_container.get("result")}
    except SandboxError as e:
        from backend.error_clean import clean_message as _cm
        msg = _cm(type(e).__name__.replace("SandboxError", "Error"), str(e))
        _log_error(db, bot.id, command.trigger, msg, "")
        if not _skip_error_handler and command.trigger != "!":
            _run_error_handler(db, bot, account, update, secrets or {}, command, e, "", bot_wrapper)
        return {"ok":False,"error":msg,"webhook_result":None}
    except Exception as e:
        from backend.error_clean import clean_message as _cm, user_stack as _us
        tb=traceback.format_exc()
        _raw_tb = tb
        tb = _us(_raw_tb, locals().get("code_to_run", ""), locals().get("preface_lines", 0))
        msg = _cm(type(e).__name__, str(e) or type(e).__name__)
        _log_error(db,bot.id,command.trigger,msg,tb)
        if not _skip_error_handler and command.trigger != "!":
            _run_error_handler(db, bot, account, update, secrets or {}, command, e, tb, bot_wrapper)
        return {"ok":False,"error":msg,"webhook_result":None}


def run_named_command(db, bot, account, trigger, update, options=None):
    if not bot: return {"ok":False,"error":"Bot context unavailable","webhook_result":None}
    cmd = db.query(models.Command).filter_by(bot_id=bot.id, trigger=trigger).first()
    if not cmd: return {"ok":False,"error":f"Command not found: {trigger}","webhook_result":None}
    return run_command(db,bot,account,cmd,update,options=options or {})


_err_notified: dict = {}


def _log_error(db, bot_id, trigger, message, tb):
    db.add(models.ErrorLog(bot_id=bot_id, command_trigger=trigger, message=message, traceback=tb)); db.commit()
    # tell the owner (at most once per bot every 30 minutes, so a failing command cannot flood the bell)
    try:
        import time as _t
        if _t.time() - _err_notified.get(bot_id, 0) > 1800:
            _err_notified[bot_id] = _t.time()
            from backend import appdb as _a
            pub = db.query(models.Bot.public_id).filter(models.Bot.id == bot_id).scalar()
            with _a.read() as _c:
                _b = _a.one(_c, "SELECT user_id,name FROM bots WHERE id=?", (pub,))
            if _b:
                _a.notify(_b["user_id"], "Bot error", f"{_b['name']}: {trigger or 'command'} failed — {str(message)[:140]}", "warning", "bot:" + str(pub))
    except Exception:
        pass


def _shift_tb(tb: str, off: int) -> str:
    """The `~` preface is prepended to the command: report line numbers relative to the command itself."""
    if not off:
        return tb
    import re as _re
    return _re.sub(r'(File "<command>", line )(\d+)', lambda m: m.group(1) + str(max(1, int(m.group(2)) - off)), tb)


def _error_details(command_trigger, exc, traceback_text=""):
    """TBC error payload — includes best-effort source line number."""
    import traceback as _tb
    import re as _re
    from backend.error_clean import redact as _red, hint_for as _hint
    exc_name = type(exc).__name__
    message = _red(str(exc) or exc_name)
    tb = traceback_text or ""
    if len(tb) > 12000:
        tb = tb[-12000:]

    line_no = None
    line_src = None
    for m in _re.finditer(r'^line (\d+)(?:: (.*))?$', tb, _re.M):       # already-cleaned stack: only the owner's own lines
        line_no = int(m.group(1))
        line_src = (m.group(2) or "").strip()
    if line_no is None:
        ms = list(_re.finditer(r'line (\d+)', tb))
        if ms:
            line_no = int(ms[-1].group(1))

    return {
        "error": message,
        "message": message,
        "name": exc_name,
        "type": exc_name,
        "command": command_trigger,
        "trigger": command_trigger,
        "line": line_no,
        "line_number": line_no,
        "line_source": line_src,
        "hint": _hint(exc_name, message),
        "traceback": tb,
    }


def _run_error_handler(db, bot, account, update, secrets, failed_command, exc, traceback_text="", bot_wrapper=None):
    """Run the optional special `!` command once. Never recurse on handler errors.

    If `!` does not exist (or itself fails), send a concise diagnostic directly to
    the current chat so bot owners/users see what went wrong instead of a silent
    webhook success.
    """
    details = _error_details(failed_command.trigger, exc, traceback_text)
    commands = db.query(models.Command).filter_by(bot_id=bot.id).all()
    handler = next((c for c in commands if c.trigger == "!"), None)
    if handler is not None and handler.id != failed_command.id:
        try:
            # TBC convention: options carries the error information and `command`
            # identifies the command that failed. Keep both structured and textual.
            handler_options = dict(details)
            handler_options["value"] = details["error"]
            # Mark error-handler context (disables Bot.runCommand per TBC rules)
            if isinstance(handler_options, dict):
                handler_options = dict(handler_options)
                handler_options["__in_error_handler"] = True
            result = run_command(
                db, bot, account, handler, update, secrets=secrets,
                options=handler_options, _skip_error_handler=True,
                capture=getattr(bot_wrapper, "_capture", None),
            )
            if result.get("ok"):
                return True
            # Do not recurse if the `!` handler itself fails.
        except Exception:
            pass

    if bot_wrapper is not None:
        chat_id = getattr(bot_wrapper, "_default_chat_id", None)
        if chat_id is not None:
            import html as _html
            where = f" (line {details['line']})" if details.get("line") else ""
            text = (f"⚠️ Error in {details['command']}{where}\n{details['type']}: {details['message']}"
                    + (f"\n→ {details['hint']}" if details.get("hint") else ""))[:3500]
            try:
                bot_wrapper.sendMessage(chat_id=chat_id, text=text, parse_mode=None)
            except Exception:
                try:
                    bot_wrapper.sendMessage(chat_id=chat_id, text=text)
                except Exception:
                    pass
    return False


def match_command(commands, update, db=None, bot_id=None):
    """TBC-compatible FAST command matching (O(1) exact lookups).

    Matching is by trigger *name* first. trigger_type is only a soft hint
    for rare catch-alls; users do not need to set command/text/any/pre/env
    manually — the platform auto-handles specials (@ ~ ! *) and exact names.

    Order:
      1. callback_query → exact / prefix match on trigger
      2. slash command (/start, /admin, …)
      3. exact text match (reply-keyboard labels)
      4. conversation state (handleNextCommand)
      5. special /handler_* triggers
      6. "*" / any fallback
    """
    msg = extract_message(update)
    text = (msg.get("text") or msg.get("caption") or "").strip()
    typ = update_type_of(update)
    uid = (msg.get("from") or {}).get("id")
    meta = {"@", "~", "!", "*"}

    # Build O(1) lookup maps once per update (typically <50 commands)
    by_trigger = {}
    by_trigger_lower = {}
    star_cmd = None
    for c in commands:
        t = c.trigger
        if t is None:
            continue
        by_trigger[t] = c
        by_trigger_lower[str(t).lower()] = c
        if t == "*":
            star_cmd = c
        # Frontend command-tab aliases (also expanded by runtime.sync_bot into separate triggers)
        for al in (getattr(c, "aliases", None) or []):
            al = str(al).strip() if al is not None else ""
            if not al or al in meta or al in by_trigger:
                continue
            by_trigger[al] = c
            by_trigger_lower[al.lower()] = c

    def _clear_state():
        if db is None or bot_id is None or uid is None:
            return
        try:
            st = db.query(models.UserState).filter_by(
                bot_id=bot_id, telegram_user_id=int(uid)
            ).first()
            if st and st.state:
                st.state = None
                st.context = {}
                db.commit()
        except Exception:
            pass

    def _load_state():
        if db is None or bot_id is None or uid is None:
            return None, None
        try:
            st = db.query(models.UserState).filter_by(
                bot_id=bot_id, telegram_user_id=int(uid)
            ).first()
            if st and st.state:
                return st, st.context or {}
        except Exception:
            pass
        return None, None

    # 1) Callback queries — exact, then prefix (sorted longest-first for speed+correctness)
    if typ == "callback_query":
        data = (msg.get("_callback_data") or "").strip()
        if data in by_trigger and data not in meta:
            _clear_state()
            return by_trigger[data], {}
        # prefix match: longest trigger first
        best = None
        best_len = -1
        for t, c in by_trigger.items():
            if t in meta or not t:
                continue
            if data.startswith(t + " ") and len(t) > best_len:
                best, best_len = c, len(t)
        if best is not None:
            _clear_state()
            return best, {}
        _clear_state()
        # Callback data is the command trigger; do not reinterpret the
        # callback message text as a normal command.
        if star_cmd is not None:
            return star_cmd, {}
        return None, {}

    # 2) Inline query
    if typ == "inline_query":
        cmd = by_trigger.get("/handler_inline_query")
        if cmd:
            return cmd, {}

    # 3) Slash commands — pure name match, ignore trigger_type
    if text.startswith("/"):
        word = text.split()[0].split("@")[0]
        if word not in meta:
            cmd = by_trigger.get(word)
            if cmd:
                _clear_state()
                return cmd, {}

    # 4) Exact text match — reply keyboard labels
    if text and text not in meta:
        cmd = by_trigger.get(text)
        if cmd:
            _clear_state()
            return cmd, {}
        cmd = by_trigger_lower.get(text.lower())
        if cmd:
            _clear_state()
            return cmd, {}
        if text in ("Back 🔙", "🔙 Back", "Back", "/cancel", "cancel"):
            _clear_state()

    # 5) Conversation state (handleNextCommand) — any message update (text or media)
    #    Slash commands / exact keyboard labels already cleared state above.
    if typ in ("message", "edited_message"):
        st, ctx = _load_state()
        if st is not None:
            cancel_at = (ctx or {}).get("cancel_at_command")
            if text and (
                (cancel_at and text.startswith(str(cancel_at)))
                or text in ("Back 🔙", "🔙 Back", "Back", "/cancel", "cancel", "❌ Cancel")
            ):
                _clear_state()
            else:
                _stn = str(st.state)
                cmd = by_trigger.get(st.state) or by_trigger.get("/" + _stn.lstrip("/")) or by_trigger.get(_stn.lstrip("/"))
                if cmd:
                    opt = (ctx or {}).get("options")
                    p = (ctx or {}).get("params")
                    if p is not None:
                        if isinstance(opt, dict):
                            wrapped = dict(opt)
                            wrapped.setdefault("params", p)
                            return cmd, wrapped
                        return cmd, {"options": opt, "params": p, "value": opt}
                    return cmd, opt

    # 6) Special update handlers — TBC uses /handler_<update_type>
    #    e.g. /handler_inline_query, /handler_my_chat_member, /handler_shipping_query
    # Callback queries are command triggers themselves; per TBC docs they do
    # not dispatch to /handler_callback_query.
    # Plain `message` updates always continue to the `*` wildcard (or slash/text
    # matches above) — never /handler_message. That keeps TBC parity:
    #   message / successful_payment / photo / ... → *
    #   pre_checkout_query / my_chat_member / ... → /handler_<type>
    if typ not in ("message", "callback_query"):
        special = f"/handler_{typ}"
        cmd = by_trigger.get(special)
        if cmd:
            return cmd, {}
    # short aliases some TBC bots use
    aliases = {
        "inline_query": ["/handler_inline_query", "/handler_inline", "on_inline"],
        "chosen_inline_result": ["/handler_chosen_inline_result", "/handler_chosen_inline"],
        "shipping_query": ["/handler_shipping_query"],
        "pre_checkout_query": ["/handler_pre_checkout_query"],
        "poll": ["/handler_poll"],
        "poll_answer": ["/handler_poll_answer"],
        "my_chat_member": ["/handler_my_chat_member"],
        "chat_member": ["/handler_chat_member"],
        "chat_join_request": ["/handler_chat_join_request"],
        "message_reaction": ["/handler_message_reaction"],
        "message_reaction_count": ["/handler_message_reaction_count"],
        "business_connection": ["/handler_business_connection"],
        "business_message": ["/handler_business_message"],
        "edited_business_message": ["/handler_edited_business_message"],
        "deleted_business_messages": ["/handler_deleted_business_messages"],
        "purchased_paid_media": ["/handler_purchased_paid_media"],
        "chat_boost": ["/handler_chat_boost"],
        "removed_chat_boost": ["/handler_removed_chat_boost"],
        "edited_message": ["/handler_edited_message"],
        "channel_post": ["/handler_channel_post"],
        "edited_channel_post": ["/handler_edited_channel_post"],
        "guest_message": ["/handler_guest_message"],
        "managed_bot": ["/handler_managed_bot"],
        "subscription": ["/handler_subscription"],
        "stopped_message_generation": ["/handler_stopped_message_generation"],
    }
    for alt in aliases.get(typ, []):
        cmd = by_trigger.get(alt)
        if cmd:
            return cmd, {}
    # Catch-all for any non-plain-message update type that has no dedicated handler
    if typ not in {"message", "callback_query"}:
        cmd = by_trigger.get("/handler_special_updates")
        if cmd:
            return cmd, {}

    # 7) * fallback (wildcard master command)
    #    - plain `message` updates always land here when no other command matched
    #    - other update types also fall through here when no /handler_* exists
    #      so users can inspect them via bot.sendMessage(message) / update_type
    if star_cmd is not None:
        return star_cmd, {}
    return None, {}


def match_webhook_command(commands, trigger):
    """Match webhook target by trigger name only — any trigger_type is valid.
    Users may point libs.Webhook.getUrlFor at /messagebro, /onWebhook, or any command.
    """
    if not trigger:
        return None
    t = str(trigger)
    for c in commands:
        if c.trigger == t:
            return c
    t2 = t.lstrip("/")
    for c in commands:
        if c.trigger and c.trigger.lstrip("/") == t2:
            return c
    return None
