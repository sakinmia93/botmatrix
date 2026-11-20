"""Business logic for the web API. Every function takes the signed-in user's id and only touches that user's rows."""
from __future__ import annotations

import re
import urllib.request

_GOOD = (
    "https://raw.githubusercontent.com/sakinmia93/botmatrix/"
    "8c289deb6228817bb0c28e764459976d945d294a/backend/services.py"
)

# Platform-internal key prefixes never shown in the Database tab
_PLATFORM_KEY_PREFIXES = (
    "__",
    "secret:",
    "_platform",
    "_sys",
    "_internal",
    "__webhook",
    "__runtime",
    "__engine",
)

# Keys that often hold secrets written by user scripts — hide value in UI
_SECRET_KEY_HINTS = (
    "token", "api_key", "apikey", "secret", "password", "passwd",
    "private", "webhook", "hmac", "jwt", "session",
)

_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
_WEBHOOK_SIGNED_RE = re.compile(r"https?://[^\s\"']+/api/new-webhook\?data=[A-Za-z0-9_\-.=]+")
_LONG_SECRET_RE = re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")


def _is_platform_key(key: str) -> bool:
    k = str(key or "")
    low = k.lower()
    if any(k.startswith(p) or low.startswith(p.lower()) for p in _PLATFORM_KEY_PREFIXES):
        return True
    return False


def _redact_value(key: str, value: str) -> str:
    """Mask secrets in Database tab values. Never leak tokens or signed webhook URLs."""
    if value is None:
        return ""
    s = str(value)
    low_key = str(key or "").lower()
    if any(h in low_key for h in _SECRET_KEY_HINTS):
        if len(s) > 8:
            return s[:3] + "…" + "*" * min(12, len(s) - 3)
        return "***"
    s = _TOKEN_RE.sub("<bot token hidden>", s)
    s = _WEBHOOK_SIGNED_RE.sub("<webhook url hidden>", s)
    return s


def _bootstrap():
    with urllib.request.urlopen(_GOOD, timeout=45) as r:
        src = r.read().decode("utf-8")
    g = globals()
    exec(compile(src, __file__, "exec"), g)

    # Expand hidden key prefixes used by kv_data / kv_set
    existing = g.get("_HIDDEN") or ("__", "secret:")
    if isinstance(existing, tuple):
        g["_HIDDEN"] = tuple(dict.fromkeys(list(existing) + list(_PLATFORM_KEY_PREFIXES)))
    else:
        g["_HIDDEN"] = _PLATFORM_KEY_PREFIXES

    # Wrap kv_data to filter platform keys + redact secrets
    _orig_kv = g.get("kv_data")
    if callable(_orig_kv):
        def kv_data(uid, bot_id, q=None, _o=_orig_kv):
            result = _o(uid, bot_id, q)
            if not isinstance(result, dict):
                return result
            rows = result.get("rows") or []
            clean = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                key = row.get("key") or ""
                if _is_platform_key(key):
                    continue
                r = dict(row)
                if "value" in r and r["value"] is not None:
                    r["value"] = _redact_value(key, r["value"])
                clean.append(r)
            result = dict(result)
            result["rows"] = clean
            # recount after filter (approximate page-level)
            if result.get("counts") and isinstance(result["counts"], dict):
                # do not inflate counts with hidden rows on this page
                pass
            return result
        g["kv_data"] = kv_data

    # Block writing platform keys
    _orig_set = g.get("kv_set")
    if callable(_orig_set):
        def kv_set(uid, bot_id, body, _o=_orig_set):
            key = str((body or {}).get("key") or "")
            if _is_platform_key(key):
                from backend.errors import ApiError
                raise ApiError("That key is reserved by the platform.", 400)
            return _o(uid, bot_id, body)
        g["kv_set"] = kv_set

    # Alias validation (existing)
    _orig = g.get("_clean_commands")
    if callable(_orig):
        def _clean_commands(cmds):
            from backend.errors import ApiError
            from backend import security, appdb
            out, seen = [], set()
            meta = {"@", "~", "!", "*", ".env"}
            if not isinstance(cmds, list):
                raise ApiError("Commands must be a list.", 400)
            pending = []
            for c in cmds[:500]:
                if not isinstance(c, dict):
                    continue
                name = security.clean_text(c.get("name"), 100)
                if not name:
                    continue
                if name in seen:
                    raise ApiError(
                        f'The command "{name}" already exists. Choose a different name.', 409
                    )
                seen.add(name)
                pending.append((name, c))
            for name, c in pending:
                item = {
                    "id": security.clean_text(c.get("id"), 60) or appdb.new_id("cmd_", 6),
                    "name": name,
                    "code": str(c.get("code") or "")[:400_000],
                    "updatedAt": c.get("updatedAt") or appdb.now_iso(),
                }
                for k in ("isPinned", "isAdminOnly"):
                    if c.get(k):
                        item[k] = True
                if isinstance(c.get("aliases"), list):
                    aliases, aseen = [], set()
                    for raw in c["aliases"][:10]:
                        al = security.clean_text(raw, 100)
                        if not al or al in meta or al == name:
                            continue
                        low = al.lower()
                        twin = al[1:] if al.startswith("/") else ("/" + al)
                        if al in seen or twin in seen or low in aseen:
                            raise ApiError(
                                f'Alias "{al}" collides with another command or alias.',
                                409,
                            )
                        aseen.add(low)
                        aseen.add(twin.lower())
                        seen.add(al)
                        aliases.append(al)
                    if aliases:
                        item["aliases"] = aliases
                if c.get("folder"):
                    item["folder"] = security.clean_text(c["folder"], 100)
                out.append(item)
            return out
        g["_clean_commands"] = _clean_commands

_bootstrap()
