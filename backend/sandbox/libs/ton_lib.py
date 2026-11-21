"""TonLib — V5R1 only + multi-asset (cryp-main style)."""
from __future__ import annotations
import pathlib
_p = pathlib.Path(__file__).with_name
_code = "".join(_p(f"v5_part_{i}.txt").read_text() for i in range(4))
exec(compile(_code, __file__, "exec"), globals())
