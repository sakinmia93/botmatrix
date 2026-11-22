"""BOT MATRIX API server — bootstrap from known-good commit + TON Connect fixes."""
from __future__ import annotations
import urllib.request

_URL = "https://raw.githubusercontent.com/sakinmia93/botmatrix/4442ba765517b8911163ba17494c3c08113480af/backend/server.py"
_code = urllib.request.urlopen(_URL, timeout=45).read().decode("utf-8")

# Patch 1: session expires KeyError
_code = _code.replace(
    '    if kind == "session" and rec["expires"] < time.time():\n        raise ApiError("This session has expired.", 410)',
    '    exp = rec.get("expires") if rec.get("expires") is not None else rec.get("exp")\n'
    '    if kind == "session" and exp is not None and float(exp) < time.time():\n'
    '        raise ApiError("This session has expired.", 410)',
)
# Patch 2: connected expires KeyError
_code = _code.replace(
    '            if rec["expires"] < time.time():\n                raise ApiError("This session has expired.", 410)',
    '            _exp = rec.get("expires") if rec.get("expires") is not None else rec.get("exp")\n'
    '            if _exp is not None and float(_exp) < time.time():\n'
    '                raise ApiError("This session has expired.", 410)',
)
# Patch 3: safe _tc_load
_code = _code.replace(
    'def _tc_load(db, em, key):\n'
    '    row = db.query(em.BotData).filter(em.BotData.key == key).first()\n'
    '    return row, (json.loads(row.value) if row else None)',
    'def _tc_load(db, em, key):\n'
    '    row = db.query(em.BotData).filter(em.BotData.key == key).first()\n'
    '    if not row:\n'
    '        return None, None\n'
    '    try:\n'
    '        return row, json.loads(row.value or "{}")\n'
    '    except Exception:\n'
    '        return row, None',
)

_ALIAS = (
    "\n\n@route(\"GET\", r\"/tonconnect/([A-Za-z0-9_\\-]{10,64})\", auth=False)\n"
    "def _tc_alias_session(x: Ctx):\n"
    "    ident = x.p(0)\n"
    "    db, em, row, rec = _tc_row(\"session\", ident)\n"
    "    db.close()\n"
    "    if not rec:\n"
    "        return (\"raw\", \"text/html; charset=utf-8\", b\"<h3>Link not found or expired.</h3>\")\n"
    "    return (\"raw\", \"text/html; charset=utf-8\", _tc_page(\"session\", ident),\n"
    "            {\"Content-Security-Policy\": \"default-src 'self' https: data: blob:; script-src 'self' 'unsafe-inline' https://unpkg.com; style-src 'self' 'unsafe-inline' https:; connect-src *; frame-ancestors 'none'\",\n"
    "             \"Cache-Control\": \"no-store\"})\n"
    "\n\n@route(\"GET\", r\"/tonconnect/req/([A-Za-z0-9_\\-]{10,64})\", auth=False)\n"
    "def _tc_alias_request(x: Ctx):\n"
    "    ident = x.p(0)\n"
    "    db, em, row, rec = _tc_row(\"request\", ident)\n"
    "    db.close()\n"
    "    if not rec:\n"
    "        return (\"raw\", \"text/html; charset=utf-8\", b\"<h3>Link not found or expired.</h3>\")\n"
    "    return (\"raw\", \"text/html; charset=utf-8\", _tc_page(\"request\", ident),\n"
    "            {\"Content-Security-Policy\": \"default-src 'self' https: data: blob:; script-src 'self' 'unsafe-inline' https://unpkg.com; style-src 'self' 'unsafe-inline' https:; connect-src *; frame-ancestors 'none'\",\n"
    "             \"Cache-Control\": \"no-store\"})\n"
)

_MARKER = (
    '@route("GET", r"/api/ton-connect/(session|request)/([A-Za-z0-9_\\-]{10,64})", auth=False)\n'
    'def _tc_view(x: Ctx):\n'
    '    kind, ident = x.p(0), x.p(1)\n'
    '    db, em, row, rec = _tc_row(kind, ident)\n'
    '    db.close()\n'
    '    if not rec:\n'
    '        return ("raw", "text/html; charset=utf-8", b"<h3>Link not found or expired.</h3>")\n'
    '    return ("raw", "text/html; charset=utf-8", _tc_page(kind, ident),\n'
    '            {"Content-Security-Policy": "default-src \'self\' https: data: blob:; script-src \'self\' \'unsafe-inline\' https://unpkg.com; style-src \'self\' \'unsafe-inline\' https:; connect-src *; frame-ancestors \'none\'",\n'
    '             "Cache-Control": "no-store"})'
)
if _MARKER in _code:
    _code = _code.replace(_MARKER, _MARKER + _ALIAS)

exec(compile(_code, "backend/server.py", "exec"), globals())
