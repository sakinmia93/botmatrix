"""libs.TelegramSession — expands tg_sess_*.b64 or tg_part_*.b64 on first import."""
from __future__ import annotations
from pathlib import Path
import base64, importlib.util, sys

_here = Path(__file__).resolve().parent
_full = _here / "_telegram_session_full.py"

def _load():
    if _full.exists() and _full.stat().st_size > 10000:
        path = _full
    else:
        parts = sorted(_here.glob("tg_sess_*.b64"), key=lambda p: int(p.stem.split("_")[-1]))
        if not parts:
            parts = sorted(_here.glob("tg_part_*.b64"), key=lambda p: int(p.stem.split("_")[1]))
        if not parts:
            raise ImportError(
                "tg_sess_*.b64 / tg_part_*.b64 missing next to telegram_session_lib.py"
            )
        data = b"".join(base64.b64decode(p.read_text().strip()) for p in parts)
        _full.write_bytes(data)
        path = _full
    spec = importlib.util.spec_from_file_location(
        "backend.sandbox.libs._telegram_session_full", path
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

_mod = _load()
TelegramSession = _mod.TelegramSession
TelegramSessionLib = getattr(_mod, "TelegramSessionLib", TelegramSession)
for _n in dir(_mod):
    if not _n.startswith("_"):
        globals()[_n] = getattr(_mod, _n)
