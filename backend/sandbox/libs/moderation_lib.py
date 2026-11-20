"""libs.Moderation — ban, mute, warn helpers."""
import time

class ModerationLib:
    def __init__(self, db=None, bot_id=None, telegram_user_id=None):
        self._db = db
        self._bot_id = bot_id
        self._uid = telegram_user_id

    def _key(self, kind, uid):
        return f"__mod_{kind}_{uid}"

    def _set(self, key, value):
        from backend import models
        from backend.sandbox.context_objects import _encode
        row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
        val = _encode(value)
        if row:
            row.value = val
        else:
            self._db.add(models.BotData(bot_id=self._bot_id, key=key, value=val))
        self._db.commit()

    def _get(self, key, default=None):
        from backend import models
        from backend.sandbox.context_objects import _decode
        row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
        return _decode(row.value) if row else default

    def _del(self, key):
        from backend import models
        row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
        if row:
            self._db.delete(row)
            self._db.commit()

    def ban(self, user_id, reason="", until=None):
        self._set(self._key("ban", user_id), {
            "reason": reason,
            "until": until,  # unix ts or None permanent
            "at": time.time(),
        })
        return True

    def unban(self, user_id):
        self._del(self._key("ban", user_id))
        return True

    def is_banned(self, user_id=None):
        uid = user_id if user_id is not None else self._uid
        data = self._get(self._key("ban", uid))
        if not data:
            return False
        until = data.get("until")
        if until and time.time() > float(until):
            self.unban(uid)
            return False
        return True

    def ban_info(self, user_id=None):
        uid = user_id if user_id is not None else self._uid
        return self._get(self._key("ban", uid))

    def warn(self, user_id, reason=""):
        key = self._key("warns", user_id)
        warns = self._get(key) or []
        if not isinstance(warns, list):
            warns = []
        warns.append({"reason": reason, "at": time.time()})
        self._set(key, warns)
        return len(warns)

    def warnings(self, user_id=None):
        uid = user_id if user_id is not None else self._uid
        return self._get(self._key("warns", uid)) or []

    def clear_warnings(self, user_id):
        self._del(self._key("warns", user_id))
        return True

    def mute(self, user_id, seconds=3600, reason=""):
        self._set(self._key("mute", user_id), {
            "until": time.time() + float(seconds),
            "reason": reason,
        })
        return True

    def unmute(self, user_id):
        self._del(self._key("mute", user_id))
        return True

    def is_muted(self, user_id=None):
        uid = user_id if user_id is not None else self._uid
        data = self._get(self._key("mute", uid))
        if not data:
            return False
        if time.time() > float(data.get("until") or 0):
            self.unmute(uid)
            return False
        return True
