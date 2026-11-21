"""TBC libs.TonLib — V5R1 + live lite-servers (no toncenter 429)."""
from __future__ import annotations
import pathlib, zlib, base64
_p = pathlib.Path(__file__).with_name
_blob = "".join(_p(f"lc{i}.b64").read_text().strip() for i in range(6))
_code = zlib.decompress(base64.b64decode(_blob)).decode("utf-8")
exec(compile(_code, str(pathlib.Path(__file__)), "exec"), globals())
