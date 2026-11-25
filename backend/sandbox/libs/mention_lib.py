"""TBC libs.Mention — mass mention (Mention-bot style). Bot API only."""
from __future__ import annotations
import time
from typing import Optional
import requests

MENTION_PREFIX = "__tgmention:"
DEFAULT_COOLDOWN = 60
MAX_TARGETS = 75
BATCH_SIZE = 5
MAX_BATCHES = 15
SEND_PAUSE_SEC = 0.35
TELEGRAM_API = "https://api.telegram.org"
_MSG = {
    "no_token": "Bot token is required for mentions.",
    "no_chat": "chat_id is required.",
    "cooldown": "Mentions are rate-limited for this chat. Please wait.",
    "no_members": "No members available to mention.",
    "forbidden": "Bot cannot list members or send messages in this chat (admin rights needed).",
    "flood": "Telegram rate limit while mentioning. Try again later.",
    "chat_not_found": "Chat not found.",
    "partial": "Some mention messages could not be sent.",
    "ok": "Mentions sent.",
}

def _err(key, code=400, **extra):
    msg = _MSG.get(key, key)
    out = {"ok": False, "success": False, "status": "error", "error": msg, "message": msg, "status_code": int(code), "timestamp": int(time.time())}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out

def _ok(**data):
    out = {"ok": True, "success": True, "status": "ok", "message": _MSG["ok"], "status_code": 200, "timestamp": int(time.time())}
    out.update(data)
    return out

def _tg(token, method, **params):
    r = requests.post(f"{TELEGRAM_API}/bot{token}/{method}", json=params, timeout=25)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": "Invalid response from Telegram"}

def _name(u):
    first = (u.get("first_name") or "").strip()
    last = (u.get("last_name") or "").strip()
    name = (first + " " + last).strip() or u.get("username") or "User"
    return name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _mention_html(u, show_names=True):
    uid = u.get("id")
    if uid is None:
        return ""
    if show_names:
        return f'<a href="tg://user?id={uid}">{_name(u)}</a>'
    return f'<a href="tg://user?id={uid}">\u2060</a>'

class MentionLib:
    def __init__(self, db=None, bot_id=None, bot_token=None):
        self._db, self._bot_id, self._bot_token = db, bot_id, bot_token

    def _token(self, bot_token=None):
        t = bot_token or self._bot_token
        if t:
            return str(t).strip()
        if self._db is not None and self._bot_id is not None:
            try:
                from backend import models
                b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
                if b and b.token:
                    return str(b.token).strip()
            except Exception:
                pass
        return None

    def _kv_get(self, key):
        if self._db is None or self._bot_id is None:
            return None
        try:
            from backend import models
            row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
            return row.value if row else None
        except Exception:
            return None

    def _kv_set(self, key, value):
        if self._db is None or self._bot_id is None:
            return
        try:
            from backend import models
            row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
            if row:
                row.value = value
            else:
                self._db.add(models.BotData(bot_id=self._bot_id, key=key, value=value))
            self._db.commit()
        except Exception:
            try:
                self._db.rollback()
            except Exception:
                pass

    def _check_cooldown(self, chat_id, cooldown):
        raw = self._kv_get(f"{MENTION_PREFIX}cd:{chat_id}")
        if not raw:
            return None
        try:
            left = cooldown - (time.time() - float(raw))
        except Exception:
            return None
        if left > 0:
            return _err("cooldown", 429, wait_seconds=int(left) + 1)
        return None

    def _mark_cooldown(self, chat_id):
        self._kv_set(f"{MENTION_PREFIX}cd:{chat_id}", str(time.time()))

    def _fetch_admins(self, token, chat_id):
        data = _tg(token, "getChatAdministrators", chat_id=chat_id)
        if not data.get("ok"):
            return []
        out = []
        for row in data.get("result") or []:
            u = row.get("user") or {}
            if u.get("is_bot") or u.get("id") is None:
                continue
            out.append(u)
        return out

    def _send_batches(self, token, chat_id, users, text, show_names, thread_id=None):
        users = users[:MAX_TARGETS]
        if not users:
            return _err("no_members", 400)
        batches = [users[i:i + BATCH_SIZE] for i in range(0, len(users), BATCH_SIZE)][:MAX_BATCHES]
        sent = failed = 0
        for bi, batch in enumerate(batches):
            links = " ".join(_mention_html(u, show_names) for u in batch if u.get("id") is not None)
            body = f"{text}\n{links}" if text else links
            payload = {"chat_id": chat_id, "text": body, "parse_mode": "HTML", "disable_web_page_preview": True}
            if thread_id is not None:
                payload["message_thread_id"] = int(thread_id)
            data = _tg(token, "sendMessage", **payload)
            if data.get("ok"):
                sent += 1
            else:
                failed += 1
                desc = (data.get("description") or "").lower()
                if "flood" in desc or "retry after" in desc:
                    return _err("flood", 429, sent_batches=sent, failed_batches=failed)
                if "forbidden" in desc:
                    return _err("forbidden", 403, sent_batches=sent, failed_batches=failed)
            if SEND_PAUSE_SEC > 0 and bi < len(batches) - 1:
                time.sleep(SEND_PAUSE_SEC)
        if sent == 0 and failed:
            return _err("partial", 502, sent_batches=0, failed_batches=failed)
        return _ok(sent_batches=sent, failed_batches=failed, mentioned=min(len(users), MAX_TARGETS), batches=len(batches))

    def everyone(self, chat_id, text="", bot_token=None, users=None, show_names=True, cooldown=DEFAULT_COOLDOWN, exclude_user_id=None, message_thread_id=None, **kw):
        token = self._token(bot_token)
        if not token:
            return _err("no_token", 400)
        if chat_id is None or chat_id == "":
            return _err("no_chat", 400)
        cd = self._check_cooldown(chat_id, int(cooldown or DEFAULT_COOLDOWN))
        if cd:
            return cd
        if users is None:
            members = self._fetch_admins(token, chat_id)
            if not members:
                chat = _tg(token, "getChat", chat_id=chat_id)
                if not chat.get("ok"):
                    return _err("forbidden", 403)
        else:
            members = list(users)[:MAX_TARGETS]
        cleaned = []
        for u in members:
            if not isinstance(u, dict) or u.get("is_bot") or u.get("id") is None:
                continue
            if exclude_user_id is not None and int(u.get("id") or 0) == int(exclude_user_id):
                continue
            cleaned.append(u)
            if len(cleaned) >= MAX_TARGETS:
                break
        result = self._send_batches(token, chat_id, cleaned, str(text or ""), bool(show_names), thread_id=message_thread_id)
        if result.get("ok"):
            self._mark_cooldown(chat_id)
        return result

    def admins(self, chat_id, text="", bot_token=None, show_names=True, cooldown=DEFAULT_COOLDOWN, exclude_user_id=None, message_thread_id=None, **kw):
        token = self._token(bot_token)
        if not token:
            return _err("no_token", 400)
        if chat_id is None or chat_id == "":
            return _err("no_chat", 400)
        cd = self._check_cooldown(chat_id, int(cooldown or DEFAULT_COOLDOWN))
        if cd:
            return cd
        admins = self._fetch_admins(token, chat_id)
        if not admins:
            return _err("no_members", 400)
        cleaned = [u for u in admins if exclude_user_id is None or int(u.get("id") or 0) != int(exclude_user_id)]
        result = self._send_batches(token, chat_id, cleaned, str(text or ""), bool(show_names), thread_id=message_thread_id)
        if result.get("ok"):
            self._mark_cooldown(chat_id)
        return result

    def mention_users(self, chat_id, users, text="", bot_token=None, show_names=True, cooldown=DEFAULT_COOLDOWN, message_thread_id=None, **kw):
        return self.everyone(chat_id, text=text, bot_token=bot_token, users=users, show_names=show_names, cooldown=cooldown, message_thread_id=message_thread_id, **kw)

    def all(self, *a, **k):
        return self.everyone(*a, **k)

    def here(self, *a, **k):
        return self.everyone(*a, **k)

Mention = MentionLib
