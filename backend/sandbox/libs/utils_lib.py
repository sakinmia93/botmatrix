"""libs.Utils — practical helpers for everyday bot development."""
from __future__ import annotations
import math
import re
import time
from typing import Any, Iterable, List, Optional


class UtilsLib:
    def __init__(self, db=None, bot_id=None, telegram_user_id=None):
        self._db = db
        self._bot_id = bot_id
        self._uid = telegram_user_id

    # ---------- lists / pagination ----------
    def chunk(self, items, size=10):
        """Split list into chunks of `size`."""
        items = list(items or [])
        size = max(1, int(size or 10))
        return [items[i:i + size] for i in range(0, len(items), size)]

    def paginate(self, items, page=1, per_page=10):
        """Return {items, page, pages, total, has_next, has_prev}."""
        items = list(items or [])
        per_page = max(1, int(per_page or 10))
        total = len(items)
        pages = max(1, math.ceil(total / per_page)) if total else 1
        page = max(1, min(int(page or 1), pages))
        start = (page - 1) * per_page
        slice_ = items[start:start + per_page]
        return {
            "items": slice_,
            "page": page,
            "pages": pages,
            "total": total,
            "per_page": per_page,
            "has_next": page < pages,
            "has_prev": page > 1,
        }

    def progress_bar(self, current, total, width=10, filled="█", empty="░"):
        """Text progress bar e.g. [████░░░░░░] 40%."""
        try:
            cur = float(current)
            tot = float(total) if float(total) else 1.0
        except Exception:
            cur, tot = 0.0, 1.0
        pct = max(0.0, min(1.0, cur / tot))
        n = int(round(pct * width))
        bar = filled * n + empty * (width - n)
        return f"[{bar}] {int(pct * 100)}%"

    # ---------- numbers / text ----------
    def format_number(self, n, decimals=0):
        try:
            n = float(n)
        except Exception:
            return str(n)
        if decimals <= 0:
            return f"{int(round(n)):,}"
        return f"{n:,.{int(decimals)}f}"

    def format_bytes(self, n):
        try:
            n = float(n)
        except Exception:
            return str(n)
        units = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while n >= 1024 and i < len(units) - 1:
            n /= 1024
            i += 1
        return f"{n:.1f} {units[i]}"

    def safe_int(self, value, default=0):
        try:
            return int(value)
        except Exception:
            return default

    def safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return default

    def truncate(self, text, length=100, suffix="…"):
        text = "" if text is None else str(text)
        if len(text) <= length:
            return text
        return text[: max(0, length - len(suffix))] + suffix

    def split_message(self, text, limit=4096):
        """Split long text for Telegram's 4096 char limit."""
        text = "" if text is None else str(text)
        limit = max(1, int(limit or 4096))
        if len(text) <= limit:
            return [text]
        parts = []
        while text:
            if len(text) <= limit:
                parts.append(text)
                break
            cut = text.rfind("\n", 0, limit)
            if cut < limit // 2:
                cut = limit
            parts.append(text[:cut])
            text = text[cut:].lstrip("\n")
        return parts

    def template(self, text, **kwargs):
        """Simple {key} replacement; missing keys stay as-is."""
        text = "" if text is None else str(text)
        def repl(m):
            key = m.group(1)
            if key in kwargs:
                return str(kwargs[key])
            return m.group(0)
        return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", repl, text)

    def mention(self, user_id, name="User"):
        """HTML mention link for Telegram."""
        return f'<a href="tg://user?id={int(user_id)}">{self._escape(name)}</a>'

    def _escape(self, s):
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def escape_html(self, s):
        return self._escape(s)

    # ---------- time ----------
    def time_ago(self, ts):
        """Human relative time from unix timestamp or datetime."""
        now = time.time()
        try:
            if hasattr(ts, "timestamp"):
                t = ts.timestamp()
            else:
                t = float(ts)
        except Exception:
            return "unknown"
        diff = max(0, int(now - t))
        if diff < 60:
            return f"{diff}s ago"
        if diff < 3600:
            return f"{diff // 60}m ago"
        if diff < 86400:
            return f"{diff // 3600}h ago"
        return f"{diff // 86400}d ago"

    def countdown(self, seconds):
        """Format seconds as H:MM:SS or M:SS."""
        try:
            s = max(0, int(seconds))
        except Exception:
            s = 0
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"

    # ---------- keyboards shortcuts ----------
    def inline_keyboard(self, rows):
        """rows = [[("Label","data"), ...], ...] or already-dict buttons."""
        kb = []
        for row in rows or []:
            line = []
            for btn in row:
                if isinstance(btn, dict):
                    line.append(btn)
                elif isinstance(btn, (list, tuple)) and len(btn) >= 2:
                    line.append({"text": str(btn[0]), "callback_data": str(btn[1])})
                else:
                    line.append({"text": str(btn), "callback_data": str(btn)})
            kb.append(line)
        return {"inline_keyboard": kb}

    def reply_keyboard(self, rows, resize=True, one_time=False):
        kb = []
        for row in rows or []:
            line = []
            for btn in row:
                if isinstance(btn, dict):
                    line.append(btn)
                else:
                    line.append({"text": str(btn)})
            kb.append(line)
        return {
            "keyboard": kb,
            "resize_keyboard": bool(resize),
            "one_time_keyboard": bool(one_time),
        }

    def remove_keyboard(self):
        return {"remove_keyboard": True}

    # ---------- admin / rate limit (DB-backed when available) ----------
    def _bot_data_get(self, key, default=None):
        if not self._db or not self._bot_id:
            return default
        try:
            from backend import models
            from backend.sandbox.context_objects import _decode
            row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
            return _decode(row.value) if row else default
        except Exception:
            return default

    def _bot_data_set(self, key, value):
        if not self._db or not self._bot_id:
            return False
        try:
            from backend import models
            from backend.sandbox.context_objects import _encode
            row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
            val = _encode(value)
            if row:
                row.value = val
            else:
                self._db.add(models.BotData(bot_id=self._bot_id, key=key, value=val))
            self._db.commit()
            return True
        except Exception:
            return False

    def set_admins(self, user_ids):
        ids = [str(x) for x in (user_ids or [])]
        return self._bot_data_set("__admins", ids)

    def get_admins(self):
        return self._bot_data_get("__admins", []) or []

    def is_admin(self, user_id=None):
        uid = str(user_id if user_id is not None else self._uid)
        return uid in [str(x) for x in self.get_admins()]

    def rate_limit(self, key, limit=5, window_seconds=60, user_id=None):
        """Return True if allowed, False if rate-limited.

        Stores hits in BotData under __rl_{user}_{key}.
        """
        uid = user_id if user_id is not None else self._uid
        store_key = f"__rl_{uid}_{key}"
        now = time.time()
        data = self._bot_data_get(store_key, {"hits": []}) or {"hits": []}
        hits = [h for h in data.get("hits", []) if now - float(h) < float(window_seconds)]
        if len(hits) >= int(limit):
            self._bot_data_set(store_key, {"hits": hits})
            return False
        hits.append(now)
        self._bot_data_set(store_key, {"hits": hits})
        return True

    def once(self, key, user_id=None):
        """Return True the first time only (per user+key), else False."""
        uid = user_id if user_id is not None else self._uid
        store_key = f"__once_{uid}_{key}"
        if self._bot_data_get(store_key):
            return False
        self._bot_data_set(store_key, True)
        return True

    def clamp(self, value, min_v=0, max_v=100):
        try:
            v = float(value)
        except Exception:
            v = float(min_v)
        return max(float(min_v), min(float(max_v), v))

    def percent(self, part, whole):
        try:
            return round(100.0 * float(part) / float(whole or 1), 2)
        except Exception:
            return 0.0

    def pick(self, mapping, key, default=None):
        """Safe dict get with default."""
        if not isinstance(mapping, dict):
            return default
        return mapping.get(key, default)

    def merge(self, *dicts):
        out = {}
        for d in dicts:
            if isinstance(d, dict):
                out.update(d)
        return out

    def unique(self, items):
        seen = set()
        out = []
        for x in items or []:
            k = str(x)
            if k in seen:
                continue
            seen.add(k)
            out.append(x)
        return out

    def yes(self, text):
        """Truthiness for user replies: yes/y/ha/হ্যাঁ/1/true."""
        t = str(text or "").strip().lower()
        return t in {"y", "yes", "yeah", "yep", "1", "true", "ok", "okay", "ha", "হ্যাঁ", "হ্যা", "জি"}

    def no(self, text):
        t = str(text or "").strip().lower()
        return t in {"n", "no", "nope", "0", "false", "na", "না"}
