"""libs.TelegramSession — single-module expand from p0..p2.b64 (no broken free vars)."""
from __future__ import annotations
from pathlib import Path
import base64, gzip, importlib.util, sys

_here = Path(__file__).resolve().parent
_full = _here / "_telegram_session_full.py"

def _data():
    parts = [(_here / f"p{i}.b64").read_text().strip() for i in range(3)]
    return gzip.decompress(base64.b64decode("".join(parts)))

def _load():
    data = _data()
    if not _full.exists() or _full.read_bytes() != data:
        _full.write_bytes(data)
    name = "backend.sandbox.libs._telegram_session_full"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, _full)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_mod = _load()
TelegramSession = _mod.TelegramSession
__all__ = ["TelegramSession"]
