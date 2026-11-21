"""TBC libs.TonLib — V5R1-only multi-asset (Tonkeeper). Loaded from compressed blob."""
from __future__ import annotations
import pathlib, zlib, base64
_p = pathlib.Path(__file__).with_name
_blob = "".join(_p(f"tb{i}.b64").read_text().strip() for i in range(8))
_code = zlib.decompress(base64.b64decode(_blob)).decode("utf-8")
exec(compile(_code, str(pathlib.Path(__file__)), "exec"), globals())
