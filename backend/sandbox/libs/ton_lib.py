"""TonLib - Tonkeeper V5R1."""
from __future__ import annotations
import base64, pathlib
_p = pathlib.Path(__file__).with_name
_code = base64.b64decode((_p("ton_lib_p1.b64").read_text().strip()+_p("ton_lib_p2.b64").read_text().strip()).encode()).decode()
exec(compile(_code, __file__, "exec"), globals())
