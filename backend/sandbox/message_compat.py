"""Compat shims for MessageObject so TBC bots can safely probe media fields."""

_MEDIA_KEYS = (
    "photo", "document", "voice", "video", "audio", "animation", "video_note",
    "sticker", "location", "contact", "reply_to_message", "forward_from",
    "forward_from_chat", "venue", "poll", "dice", "game", "story",
)

_patched = False


def patch_message_object() -> None:
    """Idempotent. Ensures `if message.audio:` never raises AttributeError."""
    global _patched
    if _patched:
        return
    from backend.sandbox.context_objects import MessageObject

    orig_init = MessageObject.__init__
    orig_getattr = MessageObject.__getattr__

    def _init(self, raw_message=None, *a, **k):
        orig_init(self, raw_message if raw_message is not None else {}, *a, **k)
        raw = getattr(self, "_raw", None) or {}
        for mk in _MEDIA_KEYS:
            if not hasattr(self, mk):
                val = raw.get(mk)
                if val in (None, "", [], {}):
                    setattr(self, mk, None)
                else:
                    try:
                        from backend.sandbox.context_objects import _deep_attr, _AttrDict
                        if isinstance(val, list):
                            setattr(self, mk, _deep_attr(val))
                        elif isinstance(val, dict):
                            setattr(self, mk, _AttrDict(val))
                        else:
                            setattr(self, mk, val)
                    except Exception:
                        setattr(self, mk, None)

    def _getattr(self, item):
        if item in _MEDIA_KEYS:
            raw = getattr(self, "_raw", None) or {}
            if item not in raw or raw.get(item) in (None, "", [], {}):
                return None
            try:
                from backend.sandbox.context_objects import _deep_attr
                return _deep_attr(raw.get(item))
            except Exception:
                return None
        return orig_getattr(self, item)

    MessageObject.__init__ = _init
    MessageObject.__getattr__ = _getattr
    _patched = True
