"""libs.PremiumGift — Telegram Stars gifts catalog + sendGift wrapper."""
import json
from pathlib import Path

_GIFTS = {
    "heart": {"gift_key": "heart", "name": "Heart", "id": "5170145012310081615", "stars": 15, "category": "Budget", "emoji": "❤️", "description": "A lovely heart"},
    "rose": {"gift_key": "rose", "name": "Rose", "id": "5170233102089322756", "stars": 25, "category": "Budget", "emoji": "🌹", "description": "A red rose"},
    "cake": {"gift_key": "cake", "name": "Cake", "id": "5170250947678437525", "stars": 50, "category": "Premium", "emoji": "🎂", "description": "Celebration cake"},
    "diamond": {"gift_key": "diamond", "name": "Diamond", "id": "5170521118301225164", "stars": 100, "category": "Luxury", "emoji": "💎", "description": "Sparkling diamond"},
    "trophy": {"gift_key": "trophy", "name": "Trophy", "id": "5168043875654172773", "stars": 100, "category": "Luxury", "emoji": "🏆", "description": "Winner trophy"},
}

class PremiumGiftLib:
    GIFTS = _GIFTS

    def __init__(self, db=None, bot_id=None, bot_token=None, storage_root=None):
        self._db = db
        self._bot_id = bot_id
        self._token = bot_token
        self._storage = storage_root

    def _hist_path(self):
        if not self._storage or not self._bot_id:
            return None
        p = Path(self._storage) / str(self._bot_id) / "gift_history.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def get_gift_catalog(self, category=None):
        items = list(_GIFTS.values())
        if category:
            items = [g for g in items if g["category"].lower() == str(category).lower()]
        return items

    def get_gift_by_key(self, gift_key):
        return _GIFTS.get(str(gift_key))

    def get_gift_by_id(self, gift_id):
        for g in _GIFTS.values():
            if str(g["id"]) == str(gift_id):
                return g
        return None

    def get_gifts_by_category(self):
        out = {}
        for g in _GIFTS.values():
            out.setdefault(g["category"], []).append(g)
        return out

    def search_gifts(self, query):
        q = str(query).lower()
        return [g for g in _GIFTS.values() if q in g["name"].lower() or q in g["description"].lower() or q in g["emoji"]]

    def get_gift_price_range(self):
        stars = [g["stars"] for g in _GIFTS.values()]
        return {"min": min(stars), "max": max(stars), "avg": sum(stars) / len(stars)}

    def _record(self, entry):
        p = self._hist_path()
        if not p:
            return
        try:
            data = json.loads(p.read_text()) if p.exists() else []
            data.insert(0, entry)
            p.write_text(json.dumps(data[:200]))
        except Exception:
            pass

    def send_gift(self, user_id, gift_key, message=None, bot_token=None):
        gift = self.get_gift_by_key(gift_key)
        if not gift:
            return {"ok": False, "error": "unknown gift_key"}
        return self.send_gift_by_id(user_id, gift["id"], message=message, bot_token=bot_token, _meta=gift)

    def send_gift_by_id(self, user_id, gift_id, message=None, bot_token=None, _meta=None):
        token = bot_token or self._token
        if not token:
            return {"ok": False, "error": "no bot token"}
        try:
            from backend.telegram.bot_wrapper import BotWrapper, TelegramAPIError
            bw = BotWrapper(token)
            kwargs = {"user_id": int(user_id), "gift_id": str(gift_id)}
            if message:
                kwargs["text"] = str(message)
            try:
                result = bw.call("sendGift", **kwargs)
            except TelegramAPIError as e:
                self._record({"ok": False, "user_id": user_id, "gift_id": gift_id, "error": e.description})
                return {"ok": False, "error": e.description, "error_code": e.error_code}
            self._record({"ok": True, "user_id": user_id, "gift_id": gift_id, "meta": _meta})
            return {"ok": True, "result": result if isinstance(result, dict) else str(result)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_gift_history(self, limit=50, status=None, recipient_id=None):
        p = self._hist_path()
        if not p or not p.exists():
            return []
        try:
            data = json.loads(p.read_text())
        except Exception:
            return []
        out = data
        if recipient_id is not None:
            out = [x for x in out if str(x.get("user_id")) == str(recipient_id)]
        if status == "ok":
            out = [x for x in out if x.get("ok")]
        elif status == "failed":
            out = [x for x in out if not x.get("ok")]
        return out[: int(limit or 50)]

    def get_gift_stats(self):
        hist = self.get_gift_history(limit=1000)
        ok = [x for x in hist if x.get("ok")]
        return {"total": len(hist), "success": len(ok), "failed": len(hist) - len(ok)}

    def set_gift_setting(self, key, value):
        p = self._hist_path()
        if not p:
            return False
        settings_p = p.parent / "gift_settings.json"
        try:
            data = json.loads(settings_p.read_text()) if settings_p.exists() else {}
            data[str(key)] = value
            settings_p.write_text(json.dumps(data))
            return True
        except Exception:
            return False

    def get_gift_setting(self, key, default=None):
        p = self._hist_path()
        if not p:
            return default
        settings_p = p.parent / "gift_settings.json"
        try:
            data = json.loads(settings_p.read_text()) if settings_p.exists() else {}
            return data.get(str(key), default)
        except Exception:
            return default

    def get_all_gift_settings(self):
        p = self._hist_path()
        if not p:
            return {}
        settings_p = p.parent / "gift_settings.json"
        try:
            return json.loads(settings_p.read_text()) if settings_p.exists() else {}
        except Exception:
            return {}

    def getGiftCatalog(self, category=None):
        return self.get_gift_catalog(category=category)
    def getGiftByKey(self, gift_key):
        return self.get_gift_by_key(gift_key)
    def getGiftHistory(self, limit=50, status=None, recipient_id=None):
        return self.get_gift_history(limit=limit, status=status, recipient_id=recipient_id)
    def getGiftPriceRange(self):
        return self.get_gift_price_range()
    def sendGift(self, user_id, gift_key, message=None, bot_token=None):
        return self.send_gift(user_id, gift_key, message=message, bot_token=bot_token)
