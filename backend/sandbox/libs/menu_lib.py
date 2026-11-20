"""libs.Menu — navigation stack for nested menus."""

class MenuLib:
    def __init__(self, db=None, bot_id=None, telegram_user_id=None):
        self._db = db
        self._bot_id = bot_id
        self._uid = telegram_user_id

    def _user(self, uid=None):
        from backend.sandbox.context_objects import UserObject
        return UserObject(self._db, self._bot_id, int(uid if uid is not None else self._uid))

    def push(self, menu_id, user_id=None):
        u = self._user(user_id)
        stack = u.getData("__menu_stack") or []
        if not isinstance(stack, list):
            stack = []
        stack.append(str(menu_id))
        u.saveData("__menu_stack", stack)
        u.saveData("__menu_current", str(menu_id))
        return stack

    def pop(self, user_id=None):
        u = self._user(user_id)
        stack = u.getData("__menu_stack") or []
        if not isinstance(stack, list):
            stack = []
        if stack:
            stack.pop()
        u.saveData("__menu_stack", stack)
        current = stack[-1] if stack else None
        u.saveData("__menu_current", current)
        return current

    def current(self, user_id=None):
        u = self._user(user_id)
        return u.getData("__menu_current")

    def stack(self, user_id=None):
        u = self._user(user_id)
        return u.getData("__menu_stack") or []

    def clear(self, user_id=None):
        u = self._user(user_id)
        u.deleteData("__menu_stack")
        u.deleteData("__menu_current")
        return True

    def buttons(self, items, cols=2, back=True):
        """Build inline keyboard from [(label, data), ...] with optional Back."""
        row, rows = [], []
        for i, it in enumerate(items or []):
            if isinstance(it, dict):
                btn = it
            elif isinstance(it, (list, tuple)) and len(it) >= 2:
                btn = {"text": str(it[0]), "callback_data": str(it[1])}
            else:
                btn = {"text": str(it), "callback_data": str(it)}
            row.append(btn)
            if len(row) >= int(cols):
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        if back:
            rows.append([{"text": "⬅️ Back", "callback_data": "menu:back"}])
        return {"inline_keyboard": rows}
