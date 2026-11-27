"""libs.TelegramSession — full Telethon MTProto (c0..c5.b64 gzip pack)."""
from __future__ import annotations
from pathlib import Path
import base64, gzip, importlib.util, sys

def _load():
    here = Path(__file__).resolve().parent
    try:
        b64 = "".join((here / f"c{i}.b64").read_text().strip() for i in range(6))
        raw = gzip.decompress(base64.b64decode(b64))
        full = here / "_telegram_session_full.py"
        full.write_bytes(raw)
        name = "backend.sandbox.libs._telegram_session_full"
        sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(name, full)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        if not hasattr(mod, "TelegramSession"):
            raise RuntimeError("TelegramSession class missing in pack")
        return mod.TelegramSession
    except Exception as e:
        class _Broken:
            def __init__(self, *a, **k):
                pass
            def __getattr__(self, n):
                raise RuntimeError(
                    "TelegramSession pack failed to load: " + str(e)[:200]
                    + " | Ensure c0.b64..c5.b64 deployed and telethon installed."
                )
        return _Broken

TelegramSession = _load()
TelegramSessionLib = TelegramSession
__all__ = ["TelegramSession", "TelegramSessionLib"]
