import re as _re


class ValidatorLib:
    """libs.Validator — quick input validation helpers for bot forms/flows."""

    _EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    _PHONE_RE = _re.compile(r"^\+?[0-9]{7,15}$")
    _URL_RE = _re.compile(r"^https?://[^\s]+$")

    def is_email(self, value):
        return bool(self._EMAIL_RE.match((value or "").strip()))

    def is_phone(self, value):
        return bool(self._PHONE_RE.match((value or "").strip().replace(" ", "")))

    def is_url(self, value):
        return bool(self._URL_RE.match((value or "").strip()))

    def is_number(self, value):
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False

    def in_range(self, value, min_val, max_val):
        try:
            v = float(value)
            return min_val <= v <= max_val
        except (TypeError, ValueError):
            return False
