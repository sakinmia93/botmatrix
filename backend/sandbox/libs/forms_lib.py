"""libs.Forms — multi-field form collection with state."""

class FormsLib:
    def __init__(self, db=None, bot_id=None, telegram_user_id=None):
        self._db = db
        self._bot_id = bot_id
        self._uid = telegram_user_id

    def _user(self, uid=None):
        from backend.sandbox.context_objects import UserObject
        return UserObject(self._db, self._bot_id, int(uid if uid is not None else self._uid))

    def start(self, name, fields, user_id=None):
        """Start form. fields = ["name", "email", ...] or [{"id":"name","prompt":"..."}]."""
        u = self._user(user_id)
        normalized = []
        for f in fields:
            if isinstance(f, dict):
                normalized.append({"id": f.get("id") or f.get("name"), "prompt": f.get("prompt") or f.get("id")})
            else:
                normalized.append({"id": str(f), "prompt": str(f)})
        state = {"form": name, "fields": normalized, "index": 0, "answers": {}}
        u.set_state(f"form:{name}", state)
        u.saveData(f"__form_{name}", state)
        return self.current_prompt(name, user_id)

    def current_prompt(self, name, user_id=None):
        u = self._user(user_id)
        state = u.getData(f"__form_{name}") or {}
        fields = state.get("fields") or []
        idx = int(state.get("index") or 0)
        if idx >= len(fields):
            return None
        return fields[idx].get("prompt") or fields[idx].get("id")

    def answer(self, name, value, user_id=None):
        """Save answer for current field; returns next prompt or None if done."""
        u = self._user(user_id)
        state = u.getData(f"__form_{name}") or {}
        fields = state.get("fields") or []
        idx = int(state.get("index") or 0)
        answers = state.get("answers") or {}
        if idx < len(fields):
            fid = fields[idx]["id"]
            answers[fid] = value
            idx += 1
        state["answers"] = answers
        state["index"] = idx
        u.saveData(f"__form_{name}", state)
        if idx >= len(fields):
            u.clear_state()
            return None
        u.set_state(f"form:{name}", state)
        return fields[idx].get("prompt") or fields[idx].get("id")

    def is_complete(self, name, user_id=None):
        u = self._user(user_id)
        state = u.getData(f"__form_{name}") or {}
        fields = state.get("fields") or []
        return int(state.get("index") or 0) >= len(fields) and len(fields) > 0

    def results(self, name, user_id=None):
        u = self._user(user_id)
        state = u.getData(f"__form_{name}") or {}
        return state.get("answers") or {}

    def cancel(self, name, user_id=None):
        u = self._user(user_id)
        u.deleteData(f"__form_{name}")
        u.clear_state()
        return True
