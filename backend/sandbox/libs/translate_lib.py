"""libs.translate — language helpers for bots (92 languages).

User level:    setUser(lang) · getUser() · clearUser()
Bot default:   setGlobal(lang) · getGlobal() · clearGlobal()
Translating:   text(string, language_code) · auto(string, message)
Validation:    supported() · languages() · is_supported(lang)

Priority when Auto-Translate is ON: the user's own choice -> the bot default ->
the language set in the user's Telegram app.
"""
from backend import translation as _t


class TranslateLib:
    def __init__(self, db=None, bot_id=None, telegram_user_id=None, storage_root=None):
        self._db = db
        self._bot_id = bot_id
        self._uid = telegram_user_id

    # ---- user level
    def setUser(self, lang, user_id=None):
        code = _t.normalize_lang(lang)
        if not code:
            raise ValueError(f"Unsupported language: {lang}")
        _t.set_user_lang(self._db, self._bot_id, user_id or self._uid, code)
        return code

    def setLang(self, lang, user_id=None):
        """Alias of setUser (kept for older bots)."""
        return self.setUser(lang, user_id)

    def getUser(self, user_id=None):
        return _t.get_user_lang(self._db, self._bot_id, user_id or self._uid)

    def clearUser(self, user_id=None):
        _t.set_user_lang(self._db, self._bot_id, user_id or self._uid, None)
        return True

    # ---- bot default
    def setGlobal(self, lang):
        code = _t.normalize_lang(lang)
        if not code:
            raise ValueError(f"Unsupported language: {lang}")
        _t.set_bot_lang(self._db, self._bot_id, code)
        return code

    def getGlobal(self):
        return _t.get_bot_lang(self._db, self._bot_id)

    def clearGlobal(self):
        _t.set_bot_lang(self._db, self._bot_id, None)
        return True

    # ---- translating
    def text(self, text, language_code):
        code = _t.normalize_lang(language_code)
        if not code:
            raise ValueError(f"Unsupported language: {language_code}")
        return _t.translate_text(str(text), code)

    def auto(self, text, message=None):
        """Translate for the sender of `message` (user choice -> bot default -> Telegram language)."""
        tg_lang = None
        try:
            tg_lang = getattr(message, "language_code", None) or (message.get("from", {}) or {}).get("language_code")
        except Exception:
            pass
        lang = _t.resolve_lang(self._db, self._bot_id, self._uid, tg_lang)
        return _t.translate_text(str(text), lang) if lang else str(text)

    # ---- validation
    def supported(self):
        return sorted(_t.LANGUAGES.keys())

    def languages(self):
        return dict(_t.LANGUAGES)

    def is_supported(self, lang):
        return _t.normalize_lang(lang) is not None

    # legacy names
    set_user = setUser
    get_user = getUser
    set_global = setGlobal
    get_global = getGlobal
    isSupported = is_supported
