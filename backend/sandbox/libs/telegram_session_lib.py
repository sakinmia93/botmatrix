"""libs.TelegramSession — loads full Telethon session lib (p0..p2.b64) or inline full module."""
from __future__ import annotations

from pathlib import Path
import base64
import gzip
import importlib.util
import sys

def _try_load_full():
    here = Path(__file__).resolve().parent
    full = here / "_telegram_session_full.py"
    try:
        pfiles = [here / f"p{i}.b64" for i in range(3)]
        if all(p.exists() for p in pfiles):
            data = gzip.decompress(base64.b64decode("".join(p.read_text().strip() for p in pfiles)))
            if b"_tg_err" in data and b"class TelegramSession" not in data:
                return None
            full.write_bytes(data)
        elif full.exists() and full.stat().st_size > 5000:
            data = full.read_bytes()
            if b"_tg_err" in data and b"class TelegramSession" not in data:
                try:
                    full.unlink()
                except Exception:
                    pass
                return None
        else:
            return None
        name = "backend.sandbox.libs._telegram_session_full"
        sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(name, full)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        if hasattr(mod, "TelegramSession"):
            return mod.TelegramSession
    except Exception as e:
        return None
    return None

_Full = _try_load_full()
if _Full is not None:
    TelegramSession = _Full
else:
    class TelegramSession:
        def __init__(self, *a, **k):
            pass
        def __getattr__(self, name):
            raise RuntimeError(
                "TelegramSession full library failed to load. "
                "Ensure p0.b64/p1.b64/p2.b64 are deployed and telethon is installed."
            )

__all__ = ["TelegramSession"]
