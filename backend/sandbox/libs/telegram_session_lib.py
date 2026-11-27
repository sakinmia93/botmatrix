"""libs.TelegramSession — full Telethon OTP (c0..c5.b64)."""
from __future__ import annotations
from pathlib import Path
import base64, importlib.util, sys

def _load():
    here = Path(__file__).resolve().parent
    try:
        b64 = "".join((here / f"c{i}.b64").read_text().strip() for i in range(6))
        raw = base64.b64decode(b64)
        full = here / "_telegram_session_full.py"
        full.write_bytes(raw)
        name = "backend.sandbox.libs._telegram_session_full"
        sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(name, full)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod.TelegramSession
    except Exception as e:
        class _Broken:
            def __init__(self, *a, **k): pass
            def __getattr__(self, n):
                raise RuntimeError("TelegramSession pack load failed: " + str(e)[:180]
                                  + " — redeploy with c0..c5.b64 + telethon")
        return _Broken

TelegramSession = _load()
TelegramSessionLib = TelegramSession
__all__ = ["TelegramSession", "TelegramSessionLib"]
