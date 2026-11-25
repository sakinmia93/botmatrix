"""Expand tg_sess_*.b64 into telegram_session_lib.py (run once after deploy)."""
from pathlib import Path
import base64
here = Path(__file__).parent
parts = sorted(here.glob("tg_sess_*.b64"))
data = b"".join(base64.b64decode(p.read_text().strip()) for p in parts)
(here / "telegram_session_lib.py").write_bytes(data)
print("wrote", here / "telegram_session_lib.py", len(data))
