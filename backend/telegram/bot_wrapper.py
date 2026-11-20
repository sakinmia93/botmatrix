"""
Dynamic Telegram Bot API wrapper — zero method allow-list.

Any attribute access like:
  bot.sendMessage(...)
  bot.send_message(...)
  bot.getChatMember(...)
  bot.some_future_method(...)

is converted to POST https://api.telegram.org/bot<token>/<MethodName>

New Telegram Bot API methods work automatically with no platform code changes.
Supports both camelCase and snake_case. Positional patterns used by TBC exports
are handled heuristically without hardcoding every method name.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import requests

from backend.telegram.html_fixer import apply_auto_html_fix
from backend.sandbox.telegram_types import markup_to_dict


class _AttrDict(dict):
    def __getattr__(self, item):
        value = self.get(item)
        if isinstance(value, dict) and not isinstance(value, _AttrDict):
            value = _AttrDict(value)
            self[item] = value
        elif isinstance(value, list):
            value = [_AttrDict(x) if isinstance(x, dict) else x for x in value]
            self[item] = value
        return value


def _wrap_result(value):
    if isinstance(value, dict):
        return _AttrDict({k: _wrap_result(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_wrap_result(v) for v in value]
    return value


TELEGRAM_API_ROOT = os.getenv("TELEGRAM_API_ROOT", "https://api.telegram.org").rstrip("/")

def _rich_html_to_telegram(html: str) -> str:
    import re
    if not html:
        return ""
    s = str(html)
    def _table_repl(m):
        body = m.group(0)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.I | re.S)
        lines = []
        for row in rows:
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.I | re.S)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if cells:
                lines.append(" | ".join(cells))
        if not lines:
            return re.sub(r"<[^>]+>", "", body)
        return "<pre>" + "\n".join(lines) + "</pre>"
    s = re.sub(r"<table[^>]*>.*?</table>", _table_repl, s, flags=re.I | re.S)
    s = re.sub(r"</?(script|style)[^>]*>", "", s, flags=re.I)
    s = re.sub(r"<caption[^>]*>(.*?)</caption>", r"<b>\1</b>\n", s, flags=re.I | re.S)
    allowed = {"b", "strong", "i", "em", "u", "s", "code", "pre", "a", "tg-emoji"}
    def _strip_tag(m):
        tag = m.group(1).lower()
        if tag in allowed:
            return m.group(0)
        return ""
    s = re.sub(r"</?([a-zA-Z0-9]+)(\s[^>]*)?>", _strip_tag, s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s[:4000]

_NO_CHAT_ID = {
    "getme", "setwebhook", "deletewebhook", "getwebhookinfo",
    "answercallbackquery", "answerinlinequery", "answerprecheckoutquery",
    "answershippingquery", "setmycommands", "deletemycommands", "getmycommands",
    "setmyname", "getmyname", "setmydescription", "getmydescription",
    "setmyshortdescription", "getmyshortdescription", "setmydefaultadministratorrights",
    "getmydefaultadministratorrights", "getupdates", "close", "logout",
    "getavailablegifts", "getmystarbalance", "getbusinessconnection",
}

_PRIMARY_PAYLOAD = {
    "sendmessage": "text", "sendphoto": "photo", "sendvideo": "video",
    "senddocument": "document", "sendaudio": "audio", "sendanimation": "animation",
    "sendvoice": "voice", "sendsticker": "sticker", "sendvideonote": "video_note",
    "sendchataction": "action", "sendlocation": "latitude", "sendvenue": "latitude",
    "sendcontact": "phone_number", "sendpoll": "question", "senddice": "emoji",
    "sendinvoice": "title", "sendgame": "game_short_name",
    "editmessagetext": "text", "editmessagecaption": "caption",
    "copymessage": "from_chat_id", "forwardmessage": "from_chat_id",
}

def _snake_to_camel(name: str) -> str:
    if not name or "_" not in name:
        return name
    parts = name.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:] if p)

def _normalize_method(name: str) -> str:
    camel = _snake_to_camel(name)
    if not camel:
        return camel
    return camel[0].upper() + camel[1:]

def _looks_like_chat_id(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("@") and len(s) > 1:
            return True
        if s.lstrip("-").isdigit() and len(s) <= 20:
            return True
    return False

def _coerce_tg_id(v):
    if v is None or isinstance(v, bool):
        return v
    if not isinstance(v, (str, int, float, bytes)) and hasattr(v, "_v"):
        try:
            inner = v._v
            if isinstance(inner, bool):
                return v
            if isinstance(inner, (int, float)):
                return int(inner)
            if isinstance(inner, str) and inner.lstrip("-").isdigit():
                return int(inner)
        except Exception:
            pass
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v == int(v):
        return int(v)
    if isinstance(v, str):
        s = v.strip().strip('"').strip("'")
        if s.lstrip("-").isdigit():
            return int(s)
        return v
    try:
        if hasattr(v, "__int__") and not isinstance(v, (str, bytes)):
            return int(v)
    except Exception:
        pass
    return v

def _to_json_str(v):
    if (
        type(v).__name__ not in ("MessageObject", "MsgFacade", "CallbackQueryObject", "_AttrDict", "_TBCOptionalStr")
        and not isinstance(v, (dict, list))
        and hasattr(v, "status_code") and hasattr(v, "text")
        and not hasattr(v, "message_id") and not hasattr(v, "update_type")
    ):
        try:
            sc = getattr(v, "status_code", None)
            if sc is None:
                raise TypeError("not a response")
            body = str(v.text or "")
            if len(body) > 3500:
                body = body[:3500] + "…"
            return f"<{sc}> {body}"
        except Exception:
            pass
    try:
        if hasattr(v, "_raw") and callable(getattr(v, "__str__", None)):
            s = str(v)
            if s and s != "None":
                return s
    except Exception:
        pass
    try:
        return json.dumps(v, ensure_ascii=False, default=str)
    except TypeError:
        return str(v)

class TelegramAPIError(Exception):
    def __init__(self, description: str, error_code: int = 0, payload: Optional[dict] = None):
        self.description = description
        self.error_code = error_code
        self.payload = payload or {}
        try:
            from backend.telegram.api_errors import enrich
            msg = enrich(description, error_code)
        except Exception:
            msg = f"[{error_code}] {description}"
        super().__init__(msg)

class BotWrapper:
    def __init__(self, token: str, default_chat_id: Optional[int] = None, timeout: int = 10,
                 default_message_id: Optional[int] = None, default_callback_query_id: Optional[str] = None,
                 capture: Optional[list] = None, pre_hook=None):
        self._capture = capture
        self._pre_hook = pre_hook
        self._token = token
        self._default_chat_id = default_chat_id
        self._default_message_id = default_message_id
        self._default_callback_query_id = default_callback_query_id
        self._timeout = timeout
        self._base = f"{TELEGRAM_API_ROOT}/bot{token}"
        self.last_response: Optional[Dict[str, Any]] = None
        self.token = token

    def call(self, method: str, **kwargs) -> Any:
        method = _normalize_method(method)
        files: Dict[str, Any] = {}
        data: Dict[str, Any] = {}
        for _tk in ("text", "caption", "question", "explanation"):
            if _tk in kwargs and kwargs[_tk] is not None and not isinstance(kwargs[_tk], (str, int, float, bool)):
                kwargs[_tk] = _to_json_str(kwargs[_tk])
        for k, v in kwargs.items():
            if v is None:
                continue
            if hasattr(v, "read"):
                files[k] = v
                continue
            if isinstance(v, str) and v.startswith("captcha://") and self._capture is None:
                try:
                    from backend import captcha_store
                    fh = captcha_store.take(v)
                    if fh is not None:
                        files[k] = fh
                        continue
                except Exception:
                    pass
            if k in ("reply_markup", "markup", "link_preview_options") or hasattr(v, "to_dict"):
                v = markup_to_dict(v)
            if k in ("chat_id", "user_id", "from_chat_id", "message_thread_id", "message_id", "reply_to_message_id") and v is not None:
                try:
                    v = _coerce_tg_id(v)
                except Exception:
                    pass
            if isinstance(v, (str, int, float, bool)):
                data[k] = v
            else:
                data[k] = _to_json_str(v)
        method_key = method.lower()
        if "chat_id" not in data and self._default_chat_id not in (None, 0, "0") and method_key not in _NO_CHAT_ID:
            data["chat_id"] = self._default_chat_id
        if "chat_id" not in data and method_key not in _NO_CHAT_ID:
            raise TelegramAPIError(f"{method}: chat_id missing", error_code=400, payload=data)
        if method_key == "answercallbackquery" and "callback_query_id" not in data and self._default_callback_query_id:
            data["callback_query_id"] = self._default_callback_query_id
        if method_key in ("editmessagetext", "editmessagecaption", "editmessagereplymarkup",
                          "editmessagemedia", "deletemessage") and "message_id" not in data:
            if self._default_message_id is not None and "inline_message_id" not in data:
                data["message_id"] = self._default_message_id
        if self._pre_hook is not None:
            try:
                data = self._pre_hook(method, data) or data
            except Exception:
                pass
        data = apply_auto_html_fix(method, data)
        if method_key in ("sendinvoice", "createinvoicelink") and "invoice_payload" in data and "payload" not in data:
            data["payload"] = data.pop("invoice_payload")
        if self._capture is not None:
            import time as _t
            self._capture.append({"method": method[:1].lower() + method[1:], "params": dict(data)})
            fake = {"message_id": 1, "date": int(_t.time()), "chat": {"id": data.get("chat_id")},
                    "text": data.get("text") or data.get("caption") or ""}
            self.last_response = {"ok": True, "result": fake}
            return _wrap_result(fake)
        req_timeout = self._timeout
        resp = None
        for attempt in range(2):
            resp = requests.post(f"{self._base}/{method}", data=data, files=files or None, timeout=req_timeout)
            if resp.status_code != 429 and resp.status_code < 500:
                break
            if attempt < 2:
                import time as _time
                try:
                    retry_after = float(resp.json().get("parameters", {}).get("retry_after", 1))
                except Exception:
                    retry_after = 1.0
                _time.sleep(min(max(retry_after, 0.25), 10.0))
        try:
            result = resp.json()
        except Exception:
            raise TelegramAPIError(f"Non-JSON Telegram response: {resp.text[:200]}", error_code=resp.status_code)
        self.last_response = result
        if not result.get("ok"):
            desc = (result.get("description") or "").lower()
            err_code = result.get("error_code", 0)
            if data.get("parse_mode") and err_code == 400 and (
                "can't parse" in desc or "parse entities" in desc or "unsupported start tag" in desc
            ):
                data_plain = dict(data)
                data_plain.pop("parse_mode", None)
                for key in ("text", "caption"):
                    if key in data_plain and isinstance(data_plain[key], str):
                        data_plain[key] = data_plain[key].replace("&", "&").replace("<", "<").replace(">", ">")
                resp2 = requests.post(f"{self._base}/{method}", data=data_plain, files=files or None, timeout=req_timeout)
                try:
                    result2 = resp2.json()
                except Exception:
                    raise TelegramAPIError(result.get("description", "error"), error_code=err_code, payload=data)
                self.last_response = result2
                if result2.get("ok"):
                    return _wrap_result(result2.get("result"))
            raise TelegramAPIError(result.get("description", "Unknown Telegram API error"), error_code=err_code, payload=data)
        return _wrap_result(result.get("result"))

    def _bind_positional(self, method_name: str, args: tuple, kwargs: dict) -> dict:
        kwargs = dict(kwargs)
        method_key = method_name.lower()
        args = list(args)
        if not args:
            return kwargs
        if method_key == "answercallbackquery":
            if "callback_query_id" not in kwargs:
                kwargs["callback_query_id"] = args.pop(0)
            if args and "text" not in kwargs:
                kwargs["text"] = args.pop(0)
            return kwargs
        if method_key == "answerinlinequery":
            if "inline_query_id" not in kwargs:
                kwargs["inline_query_id"] = args.pop(0)
            if args and "results" not in kwargs:
                kwargs["results"] = args.pop(0)
            return kwargs
        try:
            from backend.telegram.tbc_signatures import SIGNATURES
            _sig = SIGNATURES.get(method_key)
        except Exception:
            _sig = None
        if _sig:
            for _name in _sig:
                if not args:
                    break
                if _name not in kwargs:
                    kwargs[_name] = args.pop(0)
            return kwargs
        primary = _PRIMARY_PAYLOAD.get(method_key)
        if len(args) == 1:
            only = args[0]
            if method_key == "sendmessage" and "text" not in kwargs:
                kwargs["text"] = only
            elif primary and primary not in kwargs and not _looks_like_chat_id(only):
                kwargs[primary] = only
            elif "chat_id" not in kwargs and _looks_like_chat_id(only):
                kwargs["chat_id"] = only
            elif primary and primary not in kwargs:
                kwargs[primary] = only
            return kwargs
        if len(args) >= 2:
            a0, a1 = args[0], args[1]
            if "chat_id" not in kwargs and _looks_like_chat_id(a0):
                kwargs["chat_id"] = a0
                if primary and primary not in kwargs:
                    kwargs[primary] = a1
            elif primary and primary not in kwargs:
                kwargs[primary] = a0
            return kwargs
        return kwargs

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        def _caller(*args, **kwargs):
            bound = self._bind_positional(name, args, kwargs)
            return self.call(name, **bound)
        return _caller

    def replyText(self, *args, **kwargs):
        if len(args) >= 2:
            return self.sendMessage(chat_id=args[0], text=args[1], **kwargs)
        if len(args) == 1:
            return self.sendMessage(text=args[0], **kwargs)
        return self.sendMessage(**kwargs)

    def reply_text(self, *args, **kwargs):
        return self.replyText(*args, **kwargs)

    def replyMessage(self, *args, **kwargs):
        return self.replyText(*args, **kwargs)

    def reply_message(self, *args, **kwargs):
        return self.replyText(*args, **kwargs)

    def replyPhoto(self, *args, **kwargs):
        if len(args) >= 2:
            return self.sendPhoto(chat_id=args[0], photo=args[1], **kwargs)
        if len(args) == 1:
            return self.sendPhoto(photo=args[0], **kwargs)
        return self.sendPhoto(**kwargs)

    def reply_photo(self, *args, **kwargs):
        return self.replyPhoto(*args, **kwargs)

    def replyDocument(self, *args, **kwargs):
        if len(args) >= 2:
            return self.sendDocument(chat_id=args[0], document=args[1], **kwargs)
        if len(args) == 1:
            return self.sendDocument(document=args[0], **kwargs)
        return self.sendDocument(**kwargs)

    def replyTo(self, message, text, **kwargs):
        mid = getattr(message, "message_id", None) or (message.get("message_id") if isinstance(message, dict) else None)
        if mid is not None:
            kwargs.setdefault("reply_to_message_id", mid)
        return self.sendMessage(text=text, **kwargs)

    def getMe(self):
        return self.call("getMe")

    def getDefaultChatId(self):
        return self._default_chat_id

    def setWebhook(self, url: str, **kwargs):
        return self.call("setWebhook", url=url, **kwargs)

    def deleteWebhook(self, **kwargs):
        return self.call("deleteWebhook", **kwargs)

    def getFileUrl(self, file_id):
        info = self.call("getFile", file_id=file_id)
        path = info.get("file_path") if isinstance(info, dict) else getattr(info, "file_path", None)
        if not path:
            return None
        return f"{TELEGRAM_API_ROOT}/file/bot{self._token}/{path}"

    def get_file_url(self, file_id):
        return self.getFileUrl(file_id)


try:
    from backend.sandbox.message_compat import patch_message_object
    patch_message_object()
except Exception:
    pass
