class KeyboardLib:
    """libs.Keyboard — build Telegram inline/reply keyboards without hand-writing JSON."""

    def inline(self, rows):
        """
        rows: list of rows, each row a list of (text, callback_data) tuples
              or dicts like {"text": "...", "url": "..."} for link buttons.
        Example:
            libs.Keyboard.inline([[("Yes", "yes"), ("No", "no")]])
        """
        keyboard = []
        for row in rows:
            new_row = []
            for btn in row:
                if isinstance(btn, dict):
                    new_row.append(btn)
                else:
                    text, data = btn[0], btn[1]
                    new_row.append({"text": text, "callback_data": data})
            keyboard.append(new_row)
        return {"inline_keyboard": keyboard}

    def reply(self, rows, resize=True, one_time=False, placeholder=None):
        """rows: list of rows, each row a list of button label strings."""
        keyboard = [[{"text": b} if not isinstance(b, dict) else b for b in row] for row in rows]
        markup = {"keyboard": keyboard, "resize_keyboard": resize, "one_time_keyboard": one_time}
        if placeholder:
            markup["input_field_placeholder"] = placeholder
        return markup

    def remove(self):
        return {"remove_keyboard": True}

    def force_reply(self, placeholder=None):
        markup = {"force_reply": True}
        if placeholder:
            markup["input_field_placeholder"] = placeholder
        return markup
