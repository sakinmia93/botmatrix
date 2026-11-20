"""Hooks the bot runtime calls to reach platform features (start/stop/transfer).

The application server registers the real implementations at start-up.
"""
from typing import Any, Callable, Dict

_impl: Dict[str, Callable] = {}


def register(name: str, fn: Callable) -> None:
    _impl[name] = fn


def call(name: str, *args, **kwargs) -> Any:
    fn = _impl.get(name)
    if fn is None:
        return {"ok": False, "error": "not available"}
    return fn(*args, **kwargs)
