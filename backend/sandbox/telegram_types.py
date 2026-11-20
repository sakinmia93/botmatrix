"""Minimal Telegram Bot API type helpers used by many TBC-exported bots.

These are intentionally lightweight — they just build the JSON structures
Telegram expects. They exist so user code that does:

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="OK", callback_data="/start"))

works without rewriting every command.
"""
from typing import Any, List, Optional, Union


class InlineKeyboardButton:
    def __init__(
        self,
        text: str,
        url: Optional[str] = None,
        callback_data: Optional[str] = None,
        switch_inline_query: Optional[str] = None,
        switch_inline_query_current_chat: Optional[str] = None,
        web_app=None,
        login_url: Optional[dict] = None,
        pay: Optional[bool] = None,
        style: Optional[str] = None,
        icon_custom_emoji_id: Optional[str] = None,
        **kwargs,
    ):
        self._data = {"text": text}
        if url is not None:
            self._data["url"] = url
        if callback_data is not None:
            self._data["callback_data"] = callback_data
        if switch_inline_query is not None:
            self._data["switch_inline_query"] = switch_inline_query
        if switch_inline_query_current_chat is not None:
            self._data["switch_inline_query_current_chat"] = switch_inline_query_current_chat
        if web_app is not None:
            # TBC accepts either a URL string or {"url": "..."} dict
            if isinstance(web_app, str):
                self._data["web_app"] = {"url": web_app}
            else:
                self._data["web_app"] = web_app
        if login_url is not None:
            self._data["login_url"] = login_url
        if pay is not None:
            self._data["pay"] = pay
        # TBC / Bot API 7+ extensions used in modern exports
        if style is not None:
            self._data["style"] = style
        if icon_custom_emoji_id is not None:
            self._data["icon_custom_emoji_id"] = icon_custom_emoji_id
        self._data.update({k: v for k, v in kwargs.items() if v is not None})

    def to_dict(self):
        return dict(self._data)

    def __getitem__(self, key):
        return self._data[key]


class InlineKeyboardMarkup:
    def __init__(self, inline_keyboard: Optional[List] = None, **kwargs):
        self.inline_keyboard: List[List[dict]] = []
        if inline_keyboard:
            for row in inline_keyboard:
                self._add_row(row)

    def _normalize_btn(self, btn) -> dict:
        if isinstance(btn, InlineKeyboardButton):
            return btn.to_dict()
        if isinstance(btn, dict):
            return btn
        raise TypeError(f"Unsupported button type: {type(btn)}")

    def _add_row(self, row):
        if not isinstance(row, (list, tuple)):
            row = [row]
        self.inline_keyboard.append([self._normalize_btn(b) for b in row])

    def add(self, *buttons):
        """Add one or more buttons as a new row (TBC-style)."""
        if len(buttons) == 1 and isinstance(buttons[0], (list, tuple)):
            self._add_row(buttons[0])
        else:
            self._add_row(buttons)
        return self

    def row(self, *buttons):
        return self.add(*buttons)

    def to_dict(self):
        return {"inline_keyboard": self.inline_keyboard}

    # so bot.sendMessage(..., reply_markup=markup) works when the wrapper
    # json-serialises the object
    def __iter__(self):
        return iter(self.to_dict().items())

    def keys(self):
        return self.to_dict().keys()

    def get(self, key, default=None):
        return self.to_dict().get(key, default)

    def __getitem__(self, key):
        return self.to_dict()[key]


class ReplyKeyboardMarkup:
    def __init__(self, keyboard=None, resize_keyboard=True, one_time_keyboard=False,
                 input_field_placeholder=None, selective=None, **kwargs):
        # TBC: ReplyKeyboardMarkup(True) → resize_keyboard=True, empty keyboard
        if isinstance(keyboard, bool):
            resize_keyboard = keyboard
            keyboard = []
        self.keyboard = list(keyboard) if keyboard else []
        self.resize_keyboard = resize_keyboard
        self.one_time_keyboard = one_time_keyboard
        self.input_field_placeholder = input_field_placeholder
        self.selective = selective

    def add(self, *buttons):
        row = [{"text": b} if isinstance(b, str) else (b.to_dict() if hasattr(b, "to_dict") else b) for b in buttons]
        self.keyboard.append(row)
        return self

    def row(self, *buttons):
        return self.add(*buttons)

    def to_dict(self):
        d = {"keyboard": self.keyboard, "resize_keyboard": self.resize_keyboard,
             "one_time_keyboard": self.one_time_keyboard}
        if self.input_field_placeholder:
            d["input_field_placeholder"] = self.input_field_placeholder
        if self.selective is not None:
            d["selective"] = self.selective
        return d

    def get(self, key, default=None):
        return self.to_dict().get(key, default)

    def __getitem__(self, key):
        return self.to_dict()[key]


class ReplyKeyboardRemove:
    def __init__(self, remove_keyboard=True, selective=None):
        self.remove_keyboard = remove_keyboard
        self.selective = selective

    def to_dict(self):
        d = {"remove_keyboard": self.remove_keyboard}
        if self.selective is not None:
            d["selective"] = self.selective
        return d

    def get(self, key, default=None):
        return self.to_dict().get(key, default)


class ForceReply:
    def __init__(self, force_reply=True, input_field_placeholder=None, selective=None):
        self.force_reply = force_reply
        self.input_field_placeholder = input_field_placeholder
        self.selective = selective

    def to_dict(self):
        d = {"force_reply": self.force_reply}
        if self.input_field_placeholder:
            d["input_field_placeholder"] = self.input_field_placeholder
        if self.selective is not None:
            d["selective"] = self.selective
        return d

    def get(self, key, default=None):
        return self.to_dict().get(key, default)


def markup_to_dict(obj: Any) -> Any:
    """Convert keyboard helper objects (or nested structures) to plain dicts."""
    if obj is None:
        return None
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: markup_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [markup_to_dict(x) for x in obj]
    return obj


class LinkPreviewOptions:
    """Telegram Bot API link_preview_options object (Bot API 7+)."""

    def __init__(
        self,
        is_disabled: Optional[bool] = None,
        url: Optional[str] = None,
        prefer_small_media: Optional[bool] = None,
        prefer_large_media: Optional[bool] = None,
        show_above_text: Optional[bool] = None,
        **kwargs,
    ):
        self._data = {}
        if is_disabled is not None:
            self._data["is_disabled"] = bool(is_disabled)
        if url is not None:
            self._data["url"] = url
        if prefer_small_media is not None:
            self._data["prefer_small_media"] = bool(prefer_small_media)
        if prefer_large_media is not None:
            self._data["prefer_large_media"] = bool(prefer_large_media)
        if show_above_text is not None:
            self._data["show_above_text"] = bool(show_above_text)
        self._data.update({k: v for k, v in kwargs.items() if v is not None})

    def to_dict(self):
        return dict(self._data)

    def __getitem__(self, key):
        return self._data[key]


# markup_to_dict kept above


class MsgFacade:
    """TBC-compatible `msg`: the text of the incoming message, as a string-like object.

    * text message -> its text (or caption); a button press -> its callback_data (docs: "msg holds the whole callback_data")
    * a message without text (photo, contact...) -> the text `None` (docs: `if msg == "None":`)
    msg.text / msg.chat / msg.message_id still read the underlying message.
    """

    def __init__(self, message_obj):
        object.__setattr__(self, "_m", message_obj)

    @staticmethod
    def _plain(v):
        """Optional-string wrappers that hold nothing count as missing."""
        if v is None:
            return None
        if hasattr(v, "_v") and type(v).__name__ == "_TBCOptionalStr":
            return v._v
        return v

    @property
    def text(self):
        t = self._plain(getattr(self._m, "text", None))
        if t is None:
            t = self._plain(getattr(self._m, "caption", None))
        return t

    def _raw(self):
        raw = getattr(self._m, "_raw", None)
        cd = raw.get("_callback_data") if isinstance(raw, dict) else None
        return cd if cd is not None else self.text

    def _s(self):
        r = self._raw()
        return "None" if r is None else str(r)

    def strip(self, *args, **kwargs):
        return self._s().strip(*args, **kwargs)

    def split(self, *args, **kwargs):
        return self._s().split(*args, **kwargs)

    def replace(self, *args, **kwargs):
        return self._s().replace(*args, **kwargs)

    def startswith(self, *args, **kwargs):
        return self._s().startswith(*args, **kwargs)

    def endswith(self, *args, **kwargs):
        return self._s().endswith(*args, **kwargs)

    def lower(self, *args, **kwargs):
        return self._s().lower(*args, **kwargs)

    def upper(self, *args, **kwargs):
        return self._s().upper(*args, **kwargs)

    def __str__(self):
        return self._s()

    def __repr__(self):
        return f"MsgFacade({self._raw()!r})"

    def __bool__(self):
        return bool(self._raw())

    def __eq__(self, other):
        if isinstance(other, MsgFacade):
            return self._raw() == other._raw()
        if other is None:
            return self._raw() is None
        return self._s() == other

    def __hash__(self):
        return hash(self._s())

    def __contains__(self, item):
        return item in self._s()

    def __int__(self):
        return int(self._s().strip())

    def __float__(self):
        return float(self._s().strip())

    def __len__(self):
        return len(self._s())

    def __getitem__(self, key):
        if isinstance(key, str):
            if hasattr(self._m, "get"):
                return self._m.get(key)
            return getattr(self._m, key, None)
        return self._s()[key]

    def get(self, key, default=None):
        if hasattr(self._m, "get"):
            return self._m.get(key, default)
        return getattr(self._m, key, default)

    def __getattr__(self, name):
        return getattr(self._m, name)
