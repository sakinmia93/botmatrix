"""libs.Logger — lightweight activity log for bots."""
import time

class LoggerLib:
    def __init__(self, db=None, bot_id=None, max_entries=200):
        self._db = db
        self._bot_id = bot_id
        self._max = max_entries

    def _load(self):
        from backend import models
        from backend.sandbox.context_objects import _decode
        row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key="__activity_log").first()
        return (_decode(row.value) if row else []) or []

    def _save(self, entries):
        from backend import models
        from backend.sandbox.context_objects import _encode
        row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key="__activity_log").first()
        val = _encode(entries[-self._max:])
        if row:
            row.value = val
        else:
            self._db.add(models.BotData(bot_id=self._bot_id, key="__activity_log", value=val))
        self._db.commit()

    def log(self, event, user_id=None, **extra):
        entries = self._load()
        entries.append({
            "event": str(event),
            "user_id": user_id,
            "at": time.time(),
            **extra,
        })
        self._save(entries)
        return True

    def recent(self, limit=20, event=None, user_id=None):
        entries = list(reversed(self._load()))
        if event:
            entries = [e for e in entries if e.get("event") == event]
        if user_id is not None:
            entries = [e for e in entries if str(e.get("user_id")) == str(user_id)]
        return entries[: int(limit or 20)]

    def clear(self):
        self._save([])
        return True
