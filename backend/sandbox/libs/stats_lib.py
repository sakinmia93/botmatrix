"""libs.Stats — daily/total counters for bot analytics."""
import datetime

class StatsLib:
    def __init__(self, db=None, bot_id=None):
        self._db = db
        self._bot_id = bot_id

    def _today(self):
        return datetime.datetime.utcnow().strftime("%Y-%m-%d")

    def _get(self, key, default=None):
        from backend import models
        from backend.sandbox.context_objects import _decode
        row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
        return _decode(row.value) if row else default

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

    def incr(self, metric, amount=1):
        total_key = f"__stat_total_{metric}"
        day_key = f"__stat_day_{self._today()}_{metric}"
        total = int(self._get(total_key) or 0) + int(amount)
        day = int(self._get(day_key) or 0) + int(amount)
        self._set(total_key, total)
        self._set(day_key, day)
        return {"total": total, "today": day}

    def get(self, metric):
        return {
            "total": int(self._get(f"__stat_total_{metric}") or 0),
            "today": int(self._get(f"__stat_day_{self._today()}_{metric}") or 0),
        }

    def summary(self, metrics):
        return {m: self.get(m) for m in metrics}
