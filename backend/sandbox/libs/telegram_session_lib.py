"""libs.TelegramSession — expands tg_gz_*.b64 on first import."""
from __future__ import annotations
from pathlib import Path
import base64, gzip, hashlib, importlib.util, sys

_here = Path(__file__).resolve().parent
_full = _here / "_telegram_session_full.py"

def _shard_bytes() -> bytes:
    parts = sorted(_here.glob("tg_gz_*.b64"), key=lambda p: int(p.stem.split("_")[-1]))
    if not parts:
        raise ImportError("telegram_session_lib: missing tg_gz_*.b64 shards")
    return gzip.decompress(b"".join(base64.b64decode(p.read_text().strip()) for p in parts))

def _expand() -> Path:
    data = _shard_bytes()
    need = True
    if _full.exists() and _full.stat().st_size > 5000:
        try:
            old = _full.read_bytes()
            if hashlib.sha256(old).digest() == hashlib.sha256(data).digest():
                need = False
        except Exception:
            need = True
    if need:
        _full.write_bytes(data)
    return _full

def _load():
    path = _expand()
    name = "backend.sandbox.libs._telegram_session_full"
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    if not hasattr(mod, "TelegramSession"):
        raise ImportError("expanded telegram_session_lib missing TelegramSession")
    src = path.read_text(encoding="utf-8", errors="replace")
    if "_tg_err" in src:
        raise ImportError("corrupt telegram_session_lib contains _tg_err; redeploy shards")
    return mod

_mod = _load()
TelegramSession = _mod.TelegramSession
__all__ = ["TelegramSession"]
