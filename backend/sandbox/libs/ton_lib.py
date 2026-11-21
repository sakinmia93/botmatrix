"""TBC libs.TonLib — V5R1-only multi-asset (Tonkeeper). Loaded from compressed blob."""
from __future__ import annotations
import pathlib, zlib, base64
_blob = pathlib.Path(__file__).with_name("ton_blob.b64").read_text().strip()
_code = zlib.decompress(base64.b64decode(_blob)).decode("utf-8")
exec(compile(_code, str(pathlib.Path(__file__)), "exec"), globals())
