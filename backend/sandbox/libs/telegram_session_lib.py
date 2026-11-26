"""TBC libs.TelegramSession — expands tg_gz_*.b64 (gzip) on import."""
from __future__ import annotations
from pathlib import Path
import base64, gzip, sys, importlib.util
_here = Path(__file__).resolve().parent
def _ensure_full():
    full = _here / "_telegram_session_full.py"
    parts = sorted(_here.glob("tg_gz_*.b64"), key=lambda p: p.name)
    if not parts:
        old = sorted(_here.glob("tg_part_*.b64"), key=lambda p: int(p.stem.split("_")[1]))
        if not old:
            raise ImportError("tg_gz_*.b64 / tg_part_*.b64 missing")
        data = b"".join(base64.b64decode(p.read_text().strip()) for p in old)
    else:
        data = gzip.decompress(b"".join(base64.b64decode(p.read_text().strip()) for p in parts))
    if (not full.exists()) or full.stat().st_size != len(data):
        full.write_bytes(data)
    return full
_full = _ensure_full()
_spec = importlib.util.spec_from_file_location("backend.sandbox.libs._telegram_session_full", _full)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
TelegramSession = _mod.TelegramSession
TelegramSessionLib = getattr(_mod, "TelegramSessionLib", TelegramSession)
for _n in dir(_mod):
    if not _n.startswith("_"):
        globals()[_n] = getattr(_mod, _n)
