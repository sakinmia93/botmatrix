"""Lib.RefLib - TeleBot Studio referral system (link, /start tracking, counts, leaderboard, rank, stats)."""
import datetime
import hashlib
import time

_NEW_USER_WINDOW = 180      # seconds: a user whose first message is this recent counts as "new" for attribution


def _fmt(ts):
    try:
        return datetime.datetime.utcfromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None


class RefLib:
    def __init__(self, db=None, bot_id=None, telegram_user_id=None, bot_username=None):
        self._db = db
        self._bot_id = bot_id
        self._uid = telegram_user_id
        self._username = bot_username
        self._params = None          # set by the runner: the /start parameter of the running update

    # ---- helpers -----------------------------------------------------------------
    def _user(self, uid):
        from backend.sandbox.context_objects import UserObject
        return UserObject(self._db, self._bot_id, int(uid))

    def _me(self, user_id=None):
        return int(user_id if user_id is not None else self._uid)

    def _member(self, uid):
        from backend import models
        return self._db.query(models.BotMember).filter_by(bot_id=self._bot_id, telegram_user_id=int(uid)).first()

    def _info(self, uid, ts=None, prefix=None):
        m = self._member(uid)
        d = {"id": str(uid), "first_name": (m.first_name if m else None) or "", "username": (m.username if m else None), "date": _fmt(ts) if ts else None}
        if prefix:
            d["prefix"] = prefix
        return d

    def _referrals(self, uid):
        refs = self._user(uid).getData("referrals") or []
        return refs if isinstance(refs, list) else []

    # ---- legacy md5 codes (links created by earlier builds keep working) ----------------
    def _code(self, uid, campaign=None):
        base = f"{self._bot_id}:{uid}" + (f":{campaign}" if campaign else "")
        return hashlib.md5(base.encode()).hexdigest()[:8].upper()

    def _map_get(self, code):
        from backend import models
        from backend.sandbox.context_objects import _decode
        row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=f"__refmap_{str(code).upper()}").first()
        return _decode(row.value) if row else None

    # ---- links -----------------------------------------------------------------
    def getLink(self, bot_name=None, prefix=None, user_id=None, campaign=None, bot_username=None):
        """getLink(bot_name=None, prefix=None) -> https://t.me/<bot>?start=ref_<user_id>  (prefix: ref_<prefix>_<user_id>)."""
        uid = self._me(user_id)
        if bot_name is not None and str(bot_name).lstrip("-").isdigit():     # TBC style getLink(user_id, campaign)
            uid, bot_name = int(bot_name), None
            prefix = prefix or campaign
        prefix = prefix or campaign
        uname = str(bot_name or bot_username or self._username or "bot").lstrip("@")
        payload = f"ref_{prefix}_{uid}" if prefix else f"ref_{uid}"
        return f"https://t.me/{uname}?start={payload}"

    def _parse(self, payload):
        """-> (referrer_id, prefix)"""
        p = str(payload or "").strip()
        if p.startswith("/start"):
            p = p[6:].strip()
        if not p.startswith("ref_"):
            return None, None
        p = p[4:]
        parts = p.split("_")
        last = parts[-1]
        prefix = "_".join(parts[:-1]) or None
        if last.isdigit():
            return int(last), prefix
        legacy = self._map_get(last)
        return (int(legacy) if legacy else None), prefix

    def track(self, on_attracted=None, on_touch_own_link=None, on_already_attracted=None, start_payload=None, new_user_id=None):
        """Call it in the /start command. Attributes the new user to the referrer found in the start parameter.
        Returns True when the user was attributed. Self-referrals and repeated attributions are blocked."""
        if callable(on_attracted) is False and on_attracted is not None and start_payload is None:
            start_payload, on_attracted = on_attracted, None      # TBC style track("ref_...")
        payload = start_payload if start_payload is not None else self._params
        new_uid = self._me(new_user_id)
        ref, prefix = self._parse(payload)
        if not ref:
            return False
        if ref == new_uid:
            if callable(on_touch_own_link):
                on_touch_own_link()
            return False
        u = self._user(new_uid)
        m = self._member(new_uid)
        is_new = True
        if m is not None and m.first_seen is not None:
            is_new = (datetime.datetime.utcnow() - m.first_seen).total_seconds() <= _NEW_USER_WINDOW
        if u.getData("referred_by") or not is_new:
            if callable(on_already_attracted):
                on_already_attracted()
            return False
        now = time.time()
        u.saveData("referred_by", int(ref))
        u.saveData("referred_at", now)
        if prefix:
            u.saveData("referred_prefix", prefix)
        ru = self._user(ref)
        refs = self._referrals(ref)
        if new_uid not in refs:
            refs.append(new_uid)
            ru.saveData("referrals", refs)
        ru.saveData("referral_count", len(refs))
        if callable(on_attracted):
            on_attracted(self._info(ref, now, prefix))
        return True

    # ---- queries -----------------------------------------------------------------
    def getRefCount(self, user_id=None):
        return len(self._referrals(self._me(user_id)))

    def getRefList(self, user_id=None):
        out = []
        for rid in self._referrals(self._me(user_id)):
            at = self._user(rid).getData("referred_at")
            out.append(self._info(rid, at))
        return out

    def getAttractedBy(self, user_id=None):
        u = self._user(self._me(user_id))
        ref = u.getData("referred_by")
        if not ref:
            return None
        return self._info(ref, u.getData("referred_at"), u.getData("referred_prefix"))

    def _counts(self):
        from backend import models
        from backend.sandbox.context_objects import _decode
        rows = self._db.query(models.UserData).filter(models.UserData.bot_id == self._bot_id, models.UserData.key == "referral_count").all()
        c = {}
        for r in rows:
            try:
                n = int(float(_decode(r.value) or 0))
            except Exception:
                n = 0
            if n > 0:
                c[int(r.telegram_user_id)] = n
        return c

    def getTopList(self, limit=10):
        c = self._counts()
        items = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[: max(0, int(limit or 10))]
        return {str(k): v for k, v in items}

    def getRank(self, user_id=None):
        uid = self._me(user_id)
        c = self._counts()
        if uid not in c:
            return 0
        order = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
        for i, (k, _v) in enumerate(order, 1):
            if k == uid:
                return i
        return 0

    def getStats(self, user_id=None):
        uid = self._me(user_id)
        now = time.time()
        times = [self._user(r).getData("referred_at") for r in self._referrals(uid)]
        times = [float(t) for t in times if t]
        rank = self.getRank(uid)
        total_ranked = len(self._counts())
        return {
            "total": self.getRefCount(uid),
            "recent_7d": sum(1 for t in times if now - t <= 7 * 86400),
            "recent_30d": sum(1 for t in times if now - t <= 30 * 86400),
            "rank": rank,
            "top_10_percent": bool(rank and total_ranked and rank <= max(1, -(-total_ranked // 10))),
        }

    def clearUserData(self, user_id=None):
        uid = self._me(user_id)
        u = self._user(uid)
        ref = u.getData("referred_by")
        if ref:                                                  # also drop the user from the referrer's list
            ru = self._user(ref)
            refs = [x for x in self._referrals(ref) if int(x) != uid]
            ru.saveData("referrals", refs)
            ru.saveData("referral_count", len(refs))
        for k in ("referrals", "referral_count", "referred_by", "referred_at", "referred_prefix"):
            try:
                u.deleteData(k)
            except Exception:
                pass
        return True
