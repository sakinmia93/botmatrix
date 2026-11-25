"""Expand tg_part_*.b64 into telegram_session_lib.py full source."""
from pathlib import Path
import base64

here = Path(__file__).parent
parts = sorted(
    here.glob("tg_part_*.b64"),
    key=lambda p: int(p.stem.split("_")[1]),
)
if not parts:
    raise SystemExit("No tg_part_*.b64 shards found")
data = b"".join(base64.b64decode(p.read_text().strip()) for p in parts)
out = here / "telegram_session_lib.py"
out.write_bytes(data)
print("wrote", out, len(data), "bytes from", len(parts), "parts")
