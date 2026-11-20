"""
Automatic Telegram Bot API type constructors.

User code often writes:

    LinkPreviewOptions(url=..., is_disabled=False)
    ReplyParameters(message_id=123)
    InputRichMessage(html="...")
    EphemeralMessageParameters(...)

Instead of hard-coding every class from https://core.telegram.org/bots/api
(which grows with each Bot API release), any *undefined* CamelCase name is
resolved at runtime to a lightweight dict-builder that serializes via to_dict().

Official helpers we still ship explicitly (InlineKeyboardMarkup, etc.) take
priority because they implement richer behaviour (add(), web_app string, …).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class AutoTelegramType:
    """Generic Telegram input type — serializes nested objects to plain dicts."""

    def __init__(self, _type_name: str = "Object", **kwargs):
        self._type_name = _type_name
        self._data: Dict[str, Any] = {}
        for k, v in kwargs.items():
            if v is None:
                continue
            self._data[k] = v

    def to_dict(self) -> dict:
        return {k: _serialize(v) for k, v in self._data.items()}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    def __repr__(self):
        return f"{self._type_name}({self._data!r})"

    # Attribute access for user convenience
    def __getattr__(self, item):
        if item.startswith("_"):
            raise AttributeError(item)
        try:
            return self._data[item]
        except KeyError as e:
            raise AttributeError(item) from e


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(x) for x in value]
    return value


def make_type_factory(name: str):
    def factory(*args, **kwargs):
        # Rare positional: treat single dict arg as kwargs
        if args and not kwargs and len(args) == 1 and isinstance(args[0], dict):
            kwargs = dict(args[0])
        elif args and name in ("LinkPreviewOptions",) and "url" not in kwargs:
            # LinkPreviewOptions(url) short form
            if len(args) == 1 and isinstance(args[0], str):
                kwargs.setdefault("url", args[0])
        return AutoTelegramType(_type_name=name, **kwargs)

    factory.__name__ = name
    factory.__qualname__ = name
    return factory


class AutoGlobals(dict):
    """
    exec() globals that auto-define CamelCase Telegram types on first use.

    Security: only names that look like TypeNames (start with uppercase ASCII
    letter, no leading underscore) are auto-created. Everything else KeyErrors
    as usual so typos still surface as NameError.
    """

    _SKIP = frozenset({
        "True", "False", "None", "Ellipsis", "NotImplemented",
        # Python builtins that are Capitalized
        "Exception", "BaseException", "TypeError", "ValueError", "KeyError",
        "IndexError", "AttributeError", "NameError", "RuntimeError",
        "StopIteration", "GeneratorExit", "KeyboardInterrupt", "SystemExit",
        "Warning", "UserWarning", "DeprecationWarning", "ImportError",
        "OSError", "IOError", "ArithmeticError", "LookupError",
        "AssertionError", "EOFError", "FloatingPointError", "MemoryError",
        "OverflowError", "ReferenceError", "SyntaxError", "SystemError",
        "TimeoutError", "UnicodeError", "ZeroDivisionError", "BlockingIOError",
        "BrokenPipeError", "ChildProcessError", "ConnectionError",
        "FileExistsError", "FileNotFoundError", "InterruptedError",
        "IsADirectoryError", "NotADirectoryError", "PermissionError",
        "ProcessLookupError", "TimeoutError", "UnicodeDecodeError",
        "UnicodeEncodeError", "UnicodeTranslateError", "RecursionError",
    })

    def __missing__(self, key: str):
        if (
            isinstance(key, str)
            and key
            and key[0].isupper()
            and key[0].isascii()
            and not key.startswith("_")
            and key not in self._SKIP
            and key.isidentifier()
        ):
            factory = make_type_factory(key)
            self[key] = factory
            return factory
        raise KeyError(key)
