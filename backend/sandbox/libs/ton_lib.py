"""TBC libs.TonLib — V5R1-only (Tonkeeper), multi-asset, real hash. Auto-loaded from parts."""
from __future__ import annotations
import pathlib
_p = pathlib.Path(__file__).with_name
_code = "".join(_p(f"v5p{i}.txt").read_text() for i in range(3))
exec(compile(_code, str(_p("ton_lib.py")), "exec"), globals())
