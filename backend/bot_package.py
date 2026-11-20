"""Bot export / import packages (JSON, YAML, TXT).

Parts: commands, env (variables, values optional), settings (name/version/description…), data (bot + per-user database),
users (audience ids; on import they are verified through Telegram by the user-import job).
The bot token is NEVER part of a package."""
from __future__ import annotations

import json
import re
import time

import yaml

from backend import appdb, runtime, security
from backend.errors import ApiError
from backend.services import own_bot, update_bot, _clean_commands, _clean_env

PARTS = ("commands", "env", "settings", "data", "users")
FORMATS = ("json", "yaml", "txt")
MAX_SIZE = 20 * 1024 * 1024


class _Dumper(yaml.SafeDumper):
    pass


def _str_rep(d, v):
    return d.represent_scalar("tag:yaml.org,2002:str", v, style="|" if "\n" in v else None)


_Dumper.add_representer(str, _str_rep)


def _parts(raw, allowed=PARTS) -> list:
    if isinstance(raw, str):
        raw = [p for p in re.split(r"[,\s]+", raw) if p]
    out = [p for p in (raw or []) if p in allowed]
    return out or ["commands"]


# ------------------------------------------------------------------ export
def build(uid: str, bot_id: str, parts, env_values: bool = True) -> dict:
    b = own_bot(uid, bot_id)
    parts = _parts(parts)
    pkg = {"format": "botmatrix-bot", "version": 1, "exportedAt": appdb.now_iso(), "parts": parts,
           "bot": {"name": b["name"], "username": b["username"], "botId": b["bot_numeric_id"] or b["id"]}}
    if "settings" in parts:
        pkg["settings"] = {"version": b["version"] or "v1.0.0", "description": b["description"] or "", "category": b["category"] or "",
                           "miniAppTitle": b["mini_app_title"] or "", "miniAppUrl": b["mini_app_url"] or "",
                           "fasterResponse": bool(b["faster_response"]), "autoTranslate": bool(b["auto_translate"])}
    if "commands" in parts:
        pkg["commands"] = [{"name": c.get("name"), "code": c.get("code") or "", "aliases": c.get("aliases") or [],
                            "adminOnly": bool(c.get("isAdminOnly")), "pinned": bool(c.get("isPinned")), "folder": c.get("folder") or ""}
                           for c in appdb.jload(b["commands_json"], []) if c.get("name")]
    if "env" in parts:
        pkg["env"] = [{"key": e.get("key"), "value": (e.get("value") if env_values else ""), "raw": bool(e.get("raw"))}
                      for e in appdb.jload(b["env_vars_json"], []) if e.get("key")]
        pkg["envValuesIncluded"] = bool(env_values)
    if "data" in parts:
        from backend import models as em
        from backend.database import SessionLocal
        db = SessionLocal()
        try:
            pk = runtime.engine_pk(bot_id, db)
            bot_rows, user_rows = [], []
            if pk:
                for r in db.query(em.BotData).filter_by(bot_id=pk).order_by(em.BotData.key).limit(50000):
                    if not (r.key or "").startswith(("__", "secret:")):
                        bot_rows.append({"key": r.key, "value": r.value or ""})
                for r in db.query(em.UserData).filter_by(bot_id=pk).order_by(em.UserData.id).limit(200000):
                    if not (r.key or "").startswith(("__", "secret:")):
                        user_rows.append({"userId": r.telegram_user_id, "key": r.key, "value": r.value or ""})
            pkg["data"] = {"bot": bot_rows, "users": user_rows}
        finally:
            db.close()
    if "users" in parts:
        with appdb.read() as c:
            pkg["users"] = [int(r["telegram_id"]) for r in c.execute("SELECT telegram_id FROM chats WHERE bot_id=? ORDER BY rowid", (bot_id,))
                            if str(r["telegram_id"]).isdigit()]
    return pkg


def render(pkg: dict, fmt: str) -> tuple[bytes, str]:
    fmt = fmt if fmt in FORMATS else "json"
    if fmt == "json":
        return json.dumps(pkg, ensure_ascii=False, indent=2).encode(), "application/json; charset=utf-8"
    if fmt == "yaml":
        return yaml.dump(pkg, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=10_000).encode(), "text/yaml; charset=utf-8"
    out = [f"# BOT MATRIX bot export — {pkg['bot']['name']} (@{str(pkg['bot']['username']).lstrip('@')})",
           f"# exported {pkg['exportedAt']}",
           "# Edit the code below and import this file again. Each command starts with '=== name ===';",
           "# optional '#@aliases:', '#@admin', '#@pinned', '#@folder:' lines directly under the header are command options.", ""]
    if "settings" in pkg:
        out.append("=== SETTINGS ===")
        for k, v in pkg["settings"].items():
            out.append(f"{k}={json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v}")
        out.append("")
    if "env" in pkg:
        out.append("=== ENV ===")
        out += [f"{e['key']}={e['value']}" for e in pkg["env"]]
        out.append("")
    for c in pkg.get("commands", []):
        out.append(f"=== {c['name']} ===")
        if c["aliases"]:
            out.append("#@aliases: " + ", ".join(c["aliases"]))
        if c["adminOnly"]:
            out.append("#@admin")
        if c["pinned"]:
            out.append("#@pinned")
        if c["folder"]:
            out.append("#@folder: " + c["folder"])
        out += [c["code"].rstrip("\n"), ""]
    if "data" in pkg or "users" in pkg:
        out.append("# (database and users are only included in the JSON and YAML formats)")
    return "\n".join(out).encode(), "text/plain; charset=utf-8"


def export(uid, bot_id, fmt, parts, env_values=True):
    pkg = build(uid, bot_id, parts, env_values)
    body, mime = render(pkg, str(fmt).lower())
    fmt = str(fmt).lower() if str(fmt).lower() in FORMATS else "json"
    name = re.sub(r"[^A-Za-z0-9_.-]", "", str(pkg["bot"]["username"]).lstrip("@")) or "bot"
    fn = f"{name}_{'-'.join(pkg['parts'])}_{time.strftime('%Y%m%d')}.{fmt}"
    return ("raw", mime, body, {"Content-Disposition": f'attachment; filename="{fn}"', "Cache-Control": "no-store"})


# ------------------------------------------------------------------ import
def _parse_txt(text: str) -> dict:
    pkg = {"commands": [], "env": []}
    cur, buf = None, []

    def close():
        if cur is None:
            return
        body = "\n".join(buf).strip("\n")
        if cur == "ENV":
            for ln in body.splitlines():
                if "=" in ln and not ln.lstrip().startswith("#"):
                    k, v = ln.split("=", 1)
                    if k.strip():
                        pkg["env"].append({"key": k.strip(), "value": v})
        elif cur == "SETTINGS":
            st = {}
            for ln in body.splitlines():
                if "=" in ln and not ln.lstrip().startswith("#"):
                    k, v = ln.split("=", 1)
                    try:
                        st[k.strip()] = json.loads(v) if v.strip()[:1] in "{[" or v.strip() in ("true", "false") else v
                    except Exception:
                        st[k.strip()] = v
            pkg["settings"] = st
        else:
            cmd = {"name": cur, "aliases": [], "adminOnly": False, "pinned": False, "folder": ""}
            lines = body.splitlines()
            while lines and lines[0].startswith("#@"):
                m = lines.pop(0)[2:].strip()
                if m.startswith("aliases:"):
                    cmd["aliases"] = [a.strip() for a in m[8:].split(",") if a.strip()]
                elif m == "admin":
                    cmd["adminOnly"] = True
                elif m == "pinned":
                    cmd["pinned"] = True
                elif m.startswith("folder:"):
                    cmd["folder"] = m[7:].strip()
            cmd["code"] = "\n".join(lines)
            pkg["commands"].append(cmd)

    for ln in text.splitlines():
        m = re.fullmatch(r"===\s*(.+?)\s*===", ln.strip())
        if m:
            close()
            cur, buf = m.group(1), []
        elif cur is not None:
            buf.append(ln)
    close()
    return pkg


def parse(raw: bytes, filename: str = "") -> dict:
    if not raw:
        raise ApiError("Choose a JSON, YAML or TXT export file first.", 400)
    if len(raw) > MAX_SIZE:
        raise ApiError("That file is too large (max 20 MB).", 400)
    text = raw.decode("utf-8-sig", errors="replace")
    st = text.lstrip()
    try:
        if re.search(r"^===\s*.+?\s*===\s*$", text, re.M) and st[:1] not in "{[":
            pkg = _parse_txt(text)
        elif st[:1] in "{[":
            pkg = json.loads(text)
        else:
            pkg = yaml.safe_load(text)
    except (ValueError, yaml.YAMLError) as e:
        raise ApiError(f"That file could not be read: {str(e).splitlines()[0][:160]}", 400)
    if isinstance(pkg, list):
        pkg = {"commands": pkg}
    if not isinstance(pkg, dict) or not any(k in pkg for k in ("commands", "env", "settings", "data", "users")):
        raise ApiError("This file does not look like a bot export (no commands, env, data or settings found).", 400)
    return pkg


def _norm_cmd(c, i):
    name = str(c.get("name") or "").strip()
    return {"name": name, "code": str(c.get("code") or ""), "aliases": c.get("aliases") if isinstance(c.get("aliases"), list) else [],
            "isAdminOnly": bool(c.get("adminOnly", c.get("isAdminOnly"))), "isPinned": bool(c.get("pinned", c.get("isPinned"))),
            "folder": str(c.get("folder") or "")}


def preview_and_apply(uid: str, bot_id: str, raw: bytes, filename: str, parts, replace: bool, dry_run: bool = False) -> dict:
    b = own_bot(uid, bot_id)
    pkg = parse(raw, filename)
    avail = [p for p in PARTS if pkg.get(p) not in (None, [], {})]
    chosen = [p for p in _parts(parts) if p in avail] if parts else avail
    rep = {"available": avail, "applied": [], "dryRun": dry_run, "replace": replace, "skipped": []}
    body = {}
    from backend import tpy_tools

    if "commands" in chosen:
        incoming, ok_cmds = pkg.get("commands") or [], []
        for i, c in enumerate(incoming[:500]):
            if not isinstance(c, dict):
                continue
            n = _norm_cmd(c, i)
            if not n["name"]:
                rep["skipped"].append({"command": f"#{i + 1}", "reason": "missing name"})
                continue
            errs = [e for e in tpy_tools.validate(n["code"], n["name"])["errors"] if e["severity"] == "error"]
            if errs:
                rep["skipped"].append({"command": n["name"], "reason": f"line {errs[0]['line']}: {errs[0]['message']}"})
                continue
            ok_cmds.append(n)
        cur = appdb.jload(b["commands_json"], [])
        names = {c["name"]: c for c in cur}
        added = sum(1 for c in ok_cmds if c["name"] not in names)
        updated = len(ok_cmds) - added
        merged = [] if replace else list(cur)
        for n in ok_cmds:
            ex = next((m for m in merged if m.get("name") == n["name"]), None)
            if ex:
                ex.update({"code": n["code"], "aliases": n["aliases"], "isAdminOnly": n["isAdminOnly"], "isPinned": n["isPinned"],
                           "folder": n["folder"], "updatedAt": appdb.now_iso()})
            else:
                merged.append({**n, "id": appdb.new_id("cmd_", 6), "updatedAt": appdb.now_iso()})
        rep["commands"] = {"added": added, "updated": updated, "skipped": len(rep["skipped"]), "removed": (len(cur) - len([c for c in cur if c["name"] in {n['name'] for n in ok_cmds}])) if replace else 0}
        body["commands"] = merged
        rep["applied"].append("commands")
    if "env" in chosen:
        inc = [e for e in (pkg.get("env") or []) if isinstance(e, dict) and str(e.get("key") or "").strip()]
        cur = appdb.jload(b["env_vars_json"], [])
        merged = [] if replace else list(cur)
        n_new = n_upd = 0
        for e in inc[:200]:
            k = str(e["key"]).strip()
            ex = next((m for m in merged if m.get("key") == k), None)
            if ex:
                if e.get("value") not in (None, "") or replace:
                    ex["value"] = str(e.get("value") or "")
                    n_upd += 1
            else:
                merged.append({"id": appdb.new_id("env_", 4), "key": k, "value": str(e.get("value") or ""), **({"raw": True} if e.get("raw") else {})})
                n_new += 1
        rep["env"] = {"added": n_new, "updated": n_upd}
        body["envVars"] = merged
        rep["applied"].append("env")
    if "settings" in chosen and isinstance(pkg.get("settings"), dict):
        st = pkg["settings"]
        for k in ("version", "description", "category", "miniAppTitle", "miniAppUrl", "fasterResponse", "autoTranslate"):
            if k in st:
                body[k] = st[k]
        rep["settings"] = {"fields": [k for k in body if k in st]}
        rep["applied"].append("settings")
    data = pkg.get("data") if isinstance(pkg.get("data"), dict) else {}
    if "data" in chosen and data:
        rep["data"] = {"bot": len(data.get("bot") or []), "users": len(data.get("users") or [])}
        rep["applied"].append("data")
    uids = []
    if "users" in chosen and isinstance(pkg.get("users"), list):
        uids = [int(x) for x in pkg["users"] if str(x).isdigit()][:1_000_000]
        rep["users"] = {"ids": len(uids)}
        rep["applied"].append("users")
    rep["botName"] = b["name"]
    if dry_run:
        return rep
    if body:
        update_bot(uid, bot_id, body)
    if "data" in chosen and data:
        from backend import models as em
        from backend.database import SessionLocal
        db = SessionLocal()
        try:
            pk = runtime.engine_pk(bot_id, db)
            if pk:
                if replace:
                    db.query(em.BotData).filter_by(bot_id=pk).delete()
                    db.query(em.UserData).filter_by(bot_id=pk).delete()
                have = {r.key: r for r in db.query(em.BotData).filter_by(bot_id=pk)}
                for r in (data.get("bot") or [])[:50000]:
                    k = str(r.get("key") or "")
                    if not k or k.startswith(("__", "secret:")):
                        continue
                    if k in have:
                        have[k].value = str(r.get("value") or "")
                    else:
                        db.add(em.BotData(bot_id=pk, key=k, value=str(r.get("value") or "")))
                uhave = {(r.telegram_user_id, r.key): r for r in db.query(em.UserData).filter_by(bot_id=pk)}
                for r in (data.get("users") or [])[:200000]:
                    k = str(r.get("key") or "")
                    if not k or k.startswith(("__", "secret:")) or not str(r.get("userId") or "").lstrip("-").isdigit():
                        continue
                    key = (int(r["userId"]), k)
                    if key in uhave:
                        uhave[key].value = str(r.get("value") or "")
                    else:
                        db.add(em.UserData(bot_id=pk, telegram_user_id=int(r["userId"]), key=k, value=str(r.get("value") or "")))
                db.commit()
        finally:
            db.close()
    if uids:
        from backend import user_io
        rep["users"]["job"] = user_io.start_import(uid, bot_id, "\n".join(map(str, uids)).encode(), "package-users.txt")
    return rep
