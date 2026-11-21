"""TonLib — Wallet V5R1 (Tonkeeper) + v4r2 auto-detect."""
from __future__ import annotations
import base64, zlib
# Full library is zlib+base64 compressed (includes V5R1 auto-detect)
_SRC = zlib.decompress(base64.b64decode(open(__file__, "rb").read().split(b"_B64_START_\n", 1)[1].split(b"\n_B64_END_", 1)[0])).decode("utf-8") if False else None
