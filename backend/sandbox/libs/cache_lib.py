"""libs.Cache — simple TTL key/value cache stored in BotData."""
import time

class CacheLib:
    def __init__(self, db=None, bot_id=None):
        self._db = db
        self._bot_id = bot_id

    def _key(self, key):
        return f"__cache_{key}"

    def _get_row(self, key):
        if not self._db or not self._bot_id:
            return None
        from backend import models
        return self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=self._key(key)).first()

    def set(self, key, value, ttl=300):
        from backend.sandbox.context_objects import _encode
        from backend import models
        if not self._db or not self._bot_id:
            return False
        payload = {"v": value, "exp": time.time() + float(ttl or 0)}
        row = self._get_row(key)
        val = _encode(payload)
        if row:
            row.value = val
        else:
            self._db.add(models.BotData(bot_id=self._bot_id, key=self._key(key), value=val))
        self._db.commit()
        return True

    def get(self, key, default=None):
        from backend.sandbox.context_objects import _decode
        row = self._get_row(key)
        if not row:
            return default
        data = _decode(row.value) or {}
        if data.get("exp") and time.time() > float(data["exp"]):
            self.delete(key)
            return default
        return data.get("v", default)

    def delete(self, key):
        row = self._get_row(key)
        if row:
            self._db.delete(row)
            self._db.commit()
            return True
        return False

    def has(self, key):
        return self.get(key, default=Ellipsis) is not Ellipsis
