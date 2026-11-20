"""Plans & limits. Plans live in the `plans` table (seeded once, editable in the DB);
every user has `users.plan` = plan name. Limits are enforced server-side."""
import json
import os
from typing import Optional

from backend import appdb
from backend.errors import ApiError

SEED_VERSION = "4"
SEED = [
    # id, name, usd/month, points, sort, limits(-1 = unlimited), what the plan includes
    ("free", "Matrix Free", 0, 1000, 1,
     {"maxBots": 2, "maxCommandsPerBot": 20, "maxBroadcastUsers": 300, "broadcastSpeed": 5, "mediaBroadcast": False, "pinBroadcast": False,
      "richButtons": False, "userImport": False, "botTransfer": False, "storePublish": False, "databaseEdit": False, "apiAccess": False},
     ["1,000 points to start", "2 bots", "20 commands per bot", "Text broadcasts to 300 users", "Broadcast speed 5 / second",
      "Live dashboard, chats & database (view)", "User & bot export"]),
    ("pro", "Matrix Pro", 4, 40000, 2,
     {"maxBots": 10, "maxCommandsPerBot": 60, "maxBroadcastUsers": 5000, "broadcastSpeed": 15, "mediaBroadcast": True, "pinBroadcast": False,
      "richButtons": False, "userImport": True, "botTransfer": True, "storePublish": False, "databaseEdit": True, "apiAccess": False},
     ["40,000 points / month", "10 bots", "60 commands per bot", "Photo, video, audio & file broadcasts", "Broadcast to 5,000 users, 15 / second",
      "User import & export", "Send bot copies (transfer)", "Edit the database from the panel"]),
    ("growth", "Matrix Growth", 9, 150000, 3,
     {"maxBots": 30, "maxCommandsPerBot": 150, "maxBroadcastUsers": 50000, "broadcastSpeed": 30, "mediaBroadcast": True, "pinBroadcast": True,
      "richButtons": True, "userImport": True, "botTransfer": True, "storePublish": True, "databaseEdit": True, "apiAccess": True},
     ["150,000 points / month", "30 bots", "150 commands per bot", "Broadcast to 50,000 users, full 30 / second", "Pin broadcasts in every chat",
      "Rich buttons: colours, premium emoji icons, Mini Apps", "Publish to the Bot Store", "API access key"]),
    ("ultra", "Matrix Ultra", 19, 500000, 4,
     {"maxBots": -1, "maxCommandsPerBot": 500, "maxBroadcastUsers": -1, "broadcastSpeed": 1000, "mediaBroadcast": True, "pinBroadcast": True,
      "richButtons": True, "userImport": True, "botTransfer": True, "storePublish": True, "databaseEdit": True, "apiAccess": True},
     ["500,000 points / month", "Unlimited bots", "500 commands per bot", "Unlimited broadcast audience", "Turbo speed: up to 1,000 / second (Telegram paid broadcast)",
      "Everything in Growth", "Priority support"]),
]

_seeded_ok = False
_seed_lock = __import__("threading").Lock()


def seed() -> None:
    """Idempotent. Safe under concurrent traffic — only one writer runs seed."""
    global _seeded_ok
    if _seeded_ok:
        return
    with _seed_lock:
        if _seeded_ok:
            return
        import time
        last = None
        for attempt in range(8):
            try:
                with appdb.db() as c:
                    c.execute("""CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, name TEXT UNIQUE, price_usd REAL, points INTEGER,
                                 sort INTEGER, limits_json TEXT, features_json TEXT)""")
                    try:
                        cols = {r["name"] for r in c.execute("PRAGMA table_info(plans)")}
                        if "sort" not in cols:
                            c.execute("ALTER TABLE plans ADD COLUMN sort INTEGER DEFAULT 0")
                    except Exception:
                        pass
                    done = c.execute("SELECT value FROM platform_settings WHERE key='plans_seed'").fetchone()
                    need = (not done) or (done[0] != SEED_VERSION)
                    if need:
                        for pid, name, price, pts, sort, lim, feats in SEED:
                            c.execute(
                                "INSERT OR REPLACE INTO plans (id,name,price_usd,points,sort,limits_json,features_json) VALUES (?,?,?,?,?,?,?)",
                                (pid, name, price, pts, sort, json.dumps(lim), json.dumps(feats)),
                            )
                        c.execute("INSERT OR REPLACE INTO platform_settings (key,value) VALUES ('plans_seed',?)", (SEED_VERSION,))
                    c.execute("UPDATE users SET plan='Matrix Free' WHERE plan IS NULL OR plan='' OR plan IN ('Free','free')")
                    for short, full in (("Ultra", "Matrix Ultra"), ("Pro", "Matrix Pro"), ("Growth", "Matrix Growth"), ("Free", "Matrix Free")):
                        c.execute("UPDATE users SET plan=? WHERE plan=?", (full, short))
                    if not c.execute("SELECT 1 FROM platform_settings WHERE key='contact_admin_url'").fetchone():
                        c.execute("INSERT INTO platform_settings (key,value) VALUES ('contact_admin_url',?)", (os.environ.get("ADMIN_CONTACT_URL", ""),))
                _seeded_ok = True
                return
            except Exception as e:
                last = e
                msg = str(e).lower()
                if "locked" in msg or "busy" in msg:
                    time.sleep(0.05 * (attempt + 1))
                    continue
                raise
        if last:
            raise last


def _plan_dict(r) -> dict:
    return {"id": r["id"], "name": r["name"], "priceUsd": r["price_usd"], "points": r["points"],
            "limits": appdb.jload(r["limits_json"], {}), "features": appdb.jload(r["features_json"], [])}


def all_plans() -> list:
    seed()
    with appdb.read() as c:
        return [_plan_dict(r) for r in appdb.rows(c, "SELECT * FROM plans ORDER BY sort")]


def contact_url() -> str:
    with appdb.read() as c:
        r = appdb.one(c, "SELECT value FROM platform_settings WHERE key='contact_admin_url'")
    return (r["value"] if r else "") or os.environ.get("ADMIN_CONTACT_URL", "") or ""


def plan_of(uid: str) -> dict:
    try:
        seed()
    except Exception:
        # Never block plan lookup on a transient lock during seed
        pass
    with appdb.read() as c:
        u = appdb.one(c, "SELECT plan FROM users WHERE id=?", (uid,))
        name = ((u["plan"] if u else "") or "Matrix Free").strip()
        r = appdb.one(c, "SELECT * FROM plans WHERE name=? OR id=?", (name, name.lower().replace("matrix ", "")))
        if not r:
            r = appdb.one(c, "SELECT * FROM plans WHERE lower(name) LIKE ? OR lower(id)=?", (f"%{name.lower()}%", name.lower()))
        if not r:
            r = appdb.one(c, "SELECT * FROM plans WHERE id='free'")
    if not r:
        # Static fallback so broadcasts still work if plans table is mid-seed
        return {
            "id": "ultra", "name": "Matrix Ultra", "priceUsd": 19, "points": 500000,
            "limits": {"maxBots": -1, "maxCommandsPerBot": 500, "maxBroadcastUsers": -1, "broadcastSpeed": 1000,
                       "mediaBroadcast": True, "pinBroadcast": True, "richButtons": True, "userImport": True,
                       "botTransfer": True, "storePublish": True, "databaseEdit": True, "apiAccess": True},
            "features": [],
        }
    return _plan_dict(r)


def limit(uid: str, key: str):
    return plan_of(uid)["limits"].get(key)


def admins() -> list:
    raw = (os.environ.get("ADMIN_EMAILS") or "").strip()
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def check_bots(uid: str) -> None:
    p = plan_of(uid)
    mx = p["limits"].get("maxBots", -1)
    if mx is None or mx < 0:
        return
    with appdb.read() as c:
        n = appdb.one(c, "SELECT COUNT(*) n FROM bots WHERE user_id=?", (uid,))["n"]
    if n >= mx:
        raise ApiError(
            f"Your {p['name']} plan allows at most {mx} bots. Upgrade your plan or remove a bot.",
            403,
        )


def check_commands(uid: str, bot_id_or_count=None, count: int = None) -> None:
    """Accept (uid, bot_id, count) or legacy (uid, count)."""
    if count is None:
        count = int(bot_id_or_count or 0)
    else:
        count = int(count or 0)
    p = plan_of(uid)
    mx = p["limits"].get("maxCommandsPerBot", -1)
    if mx is not None and mx >= 0 and count > mx:
        raise ApiError(f"Your {p['name']} plan allows at most {mx} commands per bot.", 403)


def check_broadcast(uid: str, total: int) -> None:
    p = plan_of(uid)
    mx = p["limits"].get("maxBroadcastUsers", -1)
    if mx is not None and mx >= 0 and total > mx:
        raise ApiError(f"Your {p['name']} plan allows broadcasts to at most {mx} users.", 403)


def require(uid: str, key: str, label: str) -> None:
    if not plan_of(uid)["limits"].get(key):
        raise ApiError(f"{label} is not included in your {plan_of(uid)['name']} plan.", 403)


def grant_plan(uid: str, plan_name: str, months: int = 1, points=None) -> dict:
    import datetime as _dt
    seed()
    with appdb.db() as c:
        pl = appdb.one(c, "SELECT * FROM plans WHERE name=? OR id=?", (plan_name, str(plan_name).lower().replace("matrix ", "")))
        if not pl:
            pl = appdb.one(c, "SELECT * FROM plans WHERE lower(name) LIKE ?", (f"%{str(plan_name).lower()}%",))
        if not pl:
            raise ApiError("Unknown plan.", 404)
        c.execute("UPDATE users SET plan=? WHERE id=?", (pl["name"], uid))
        try:
            if pl["id"] != "free" and months and int(months) > 0:
                exp = (appdb.utcnow() + _dt.timedelta(days=int(months) * 30)).isoformat(timespec="seconds") + "Z"
                c.execute("UPDATE users SET plan_expires_at=? WHERE id=?", (exp, uid))
            elif pl["id"] == "free":
                c.execute("UPDATE users SET plan_expires_at=NULL WHERE id=?", (uid,))
        except Exception:
            pass
        if points is not None:
            c.execute("UPDATE users SET points=? WHERE id=?", (max(0, int(points)), uid))
        elif pl["points"] is not None:
            c.execute("UPDATE users SET points=? WHERE id=?", (max(0, int(pl["points"] or 0)), uid))
    return {"ok": True, "plan": pl["name"]}


def expire_plans_tick() -> int:
    n = 0
    try:
        now = appdb.now_iso()
        with appdb.db() as c:
            rows = appdb.rows(
                c,
                "SELECT id FROM users WHERE plan_expires_at IS NOT NULL AND plan_expires_at != '' "
                "AND plan_expires_at < ? AND plan NOT IN ('Matrix Free','Free')",
                (now,),
            )
            for r in rows:
                c.execute("UPDATE users SET plan=?, plan_expires_at=NULL WHERE id=?", ("Matrix Free", r["id"]))
                n += 1
    except Exception:
        pass
    return n


def monthly_free_reset_tick() -> int:
    n = 0
    try:
        month_key = appdb.utcnow().strftime("%Y-%m")
        free_pts = 1000
        with appdb.read() as c:
            pl = appdb.one(c, "SELECT points FROM plans WHERE id='free' LIMIT 1")
            if pl:
                free_pts = int(pl["points"] or 1000)
        with appdb.db() as c:
            rows = appdb.rows(c, "SELECT id, last_free_reset FROM users WHERE plan IN ('Matrix Free','Free') OR plan IS NULL OR plan=''")
            for r in rows:
                last = r["last_free_reset"] if "last_free_reset" in r.keys() else None
                if last and str(last).startswith(month_key):
                    continue
                c.execute("UPDATE users SET points=?, last_free_reset=? WHERE id=?", (free_pts, month_key, r["id"]))
                n += 1
    except Exception:
        pass
    return n
