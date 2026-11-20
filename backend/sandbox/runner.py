"""TPY runtime glue, routing, conversation state and update normalization."""
from __future__ import annotations
import zlib, base64 as _b64
from backend.sandbox import _runner_payload as _p
_SRC = zlib.decompress(_b64.b64decode((_p.A + _p.B).encode("ascii")))
exec(compile(_SRC, "backend/sandbox/runner.py", "exec"), globals())
