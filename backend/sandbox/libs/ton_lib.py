"""TBC libs.TonLib — V5R1 + live lite-servers (no toncenter 429)."""
from __future__ import annotations
import pathlib
_p = pathlib.Path(__file__).with_name
_code = "".join(_p(f"cp{i}.txt").read_text() for i in range(4))
exec(compile(_code, str(_p("ton_lib.py")), "exec"), globals())
