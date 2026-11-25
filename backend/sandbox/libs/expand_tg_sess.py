"""Expand tg_part_*.b64 into telegram_session_lib.py full source."""
from pathlib import Path
import base64
here = Path(__file__).parent
parts = sorted(here.glob("tg_part_*.b64"), key=lambda p: int(p.stem.split("_")[1]))
if not parts:
    parts = sorted(here.glob("tg_sess_*.b64"))
data = b"".join(base64.b64decode(p.read_text().strip()) for p in parts)
(here / "telegram_session_lib.py").write_bytes(data)
print("wrote telegram_session_lib.py", len(data), "bytes from", len(parts), "parts")
