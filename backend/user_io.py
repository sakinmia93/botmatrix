"""Bot audience Import / Export.

Import: JSON / CSV / TXT with Telegram user ids -> every id is verified through Telegram (getChat) so only users that
really started the bot (and are reachable) are added. ~10 verifications per second. Existing users and data stay untouched.
Export: streams the audience to a JSON or CSV file in the background (fixed memory, millions of rows in seconds)."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from backend import appdb, security, tg
from backend.errors import ApiError
from backend.services import own_bot

IMPORT_RATE = 10.0            # verifications per second
MAX_IMPORT_IDS = 1_000_000
EXPORT_DIR = os.path.join(tempfile.gettempdir(), "bm_exports")
JOBS: dict = {}
_LOCK = threading.Lock()
_COLORS = ["blue", "emerald", "violet", "amber", "rose", "cyan", "indigo", "teal"]
_ID_KEYS = ("telegram_id", "telegramid", "user_id", "userid", "chat_id", "chatid", "tg_id", "id")


# ------------------------------------------------------------------ parsing
def _as_id(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and float(v).is_integer():
        v = int(v)
    elif isinstance(v, str) and re.fullmatch(r"\s*\d{1,15}\s*", v):
        v = int(v)
    else:
        return None
    return v if 0 < v < 2 ** 52 else None


def parse_ids(raw: bytes, filename: str = "") -> tuple[list, int]:
    """-> (unique ids in file order, number of entries that were not valid ids)"""
    text = raw.decode("utf-8-sig", errors="ignore")
    ids, seen, bad = [], set(), 0

    def add(v):
        nonlocal bad
        i = _as_id(v)
        if i is None:
            bad += 1
        elif i not in seen:
            seen.add(i)
            ids.append(i)

    stripped = text.lstrip()
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "json" or stripped[:1] in "[{":
        try:
            data = json.loads(text)
        except Exception:
            raise ApiError("That JSON file could not be read.", 400)
        if isinstance(data, dict):
            for k in ("users", "ids", "user_ids", "data", "items"):
                if isinstance(data.get(k), list):
                    data = data[k]
                    break
            else:
                data = list(data.values()) if all(isinstance(v, (dict, int, str)) for v in data.values()) and not any(k in data for k in _ID_KEYS) else [data]
        if not isinstance(data, list):
            raise ApiError("The JSON file must contain a list of user ids.", 400)
        for it in data:
            if isinstance(it, dict):
                low = {str(k).lower(): v for k, v in it.items()}
                v = next((low[k] for k in _ID_KEYS if k in low), None)
                add(v)
            else:
                add(it)
    elif ext == "csv" or ("," in text.split("\n", 1)[0] and ext != "txt") or ";" in text.split("\n", 1)[0]:
        dialect = csv.excel
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except Exception:
            pass
        rows = list(csv.reader(io.StringIO(text), dialect))
        col, start = 0, 0
        if rows:
            head = [c.strip().lower().replace(" ", "_") for c in rows[0]]
            if not any(_as_id(c) for c in rows[0]):
                start = 1
                for k in _ID_KEYS:
                    if k in head:
                        col = head.index(k)
                        break
        for r in rows[start:]:
            if r and any(c.strip() for c in r):
                add(r[col] if col < len(r) else "")
    else:
        for tok in re.split(r"[\s,;]+", text):
            if tok:
                add(tok)
    if len(ids) > MAX_IMPORT_IDS:
        raise ApiError(f"Too many users in one file (max {MAX_IMPORT_IDS:,}). Split the file and import in parts.", 400)
    return ids, bad


# ------------------------------------------------------------------ jobs
def _public(j: dict) -> dict:
    out = {k: v for k, v in j.items() if k not in ("uid", "path", "cancel")}
    el = (j.get("finishedAt") or time.time()) - j["startedAt"]
    out["elapsed"] = round(el, 1)
    if j["kind"] == "import" and j["state"] == "running" and j["processed"] > 0 and j["toVerify"] > 0:
        out["etaSeconds"] = int(max(0, (j["toVerify"] - j["processed"]) / max(0.1, j["processed"] / max(el, 0.1))))
    out["percent"] = 100 if j["state"] == "done" else (int(100 * (j["processed"] / j["total"])) if j.get("total") else 0)
    return out


def _new_job(uid, bot_id, kind, **extra) -> dict:
    with _LOCK:
        for j in JOBS.values():
            if j["botId"] == bot_id and j["kind"] == kind and j["state"] == "running":
                raise ApiError(f"An {kind} is already running for this bot.", 409, {"job": _public(j)})
        old = sorted((j for j in JOBS.values() if j["uid"] == uid and j["state"] != "running"), key=lambda j: j["startedAt"])
        for j in old[:-9]:
            _drop(j["id"])
        j = {"id": appdb.new_id("job_", 6), "uid": uid, "botId": bot_id, "kind": kind, "state": "running",
             "startedAt": time.time(), "finishedAt": None, "processed": 0, "total": 0, "error": "", "cancel": False, **extra}
        JOBS[j["id"]] = j
    _sweep_files()
    return j


def _drop(jid):
    j = JOBS.pop(jid, None)
    if j and j.get("path"):
        try:
            os.remove(j["path"])
        except OSError:
            pass


def _sweep_files():
    try:
        for n in os.listdir(EXPORT_DIR):
            p = os.path.join(EXPORT_DIR, n)
            if time.time() - os.path.getmtime(p) > 3600:
                os.remove(p)
    except OSError:
        pass


def get_job(uid, bot_id, jid) -> dict:
    j = JOBS.get(jid)
    if not j or j["uid"] != uid or j["botId"] != bot_id:
        raise ApiError("That job was not found (it may have expired).", 404)
    return j


def status(uid, bot_id, jid) -> dict:
    own_bot(uid, bot_id)
    return _public(get_job(uid, bot_id, jid))


def cancel(uid, bot_id, jid) -> dict:
    own_bot(uid, bot_id)
    j = get_job(uid, bot_id, jid)
    j["cancel"] = True
    return _public(j)


def active(uid, bot_id) -> dict:
    """the newest job of each kind (so the page can pick the progress back up after a reload)"""
    own_bot(uid, bot_id)
    out = {}
    for j in sorted(JOBS.values(), key=lambda j: j["startedAt"]):
        if j["uid"] == uid and j["botId"] == bot_id:
            out[j["kind"]] = _public(j)
    return out


# ------------------------------------------------------------------ import
class _Limiter:
    def __init__(self, rate):
        self.gap, self.next, self.lock = 1.0 / rate, time.monotonic(), threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.gap
        if t > now:
            time.sleep(t - now)


def start_import(uid: str, bot_id: str, raw: bytes, filename: str) -> dict:
    b = own_bot(uid, bot_id)
    token = security.decrypt(b["token"]) if b["token"] else ""
    if not token:
        raise ApiError("Add a valid bot token first — users are verified through Telegram with your bot's token.", 400)
    if not raw:
        raise ApiError("Choose a JSON, CSV or TXT file with Telegram user ids.", 400)
    ids, bad = parse_ids(raw, filename)
    if not ids:
        raise ApiError("No valid Telegram user ids were found in that file.", 400)
    try:
        tg.get_me(token)
    except tg.TgError:
        raise ApiError("Your bot token is not valid right now, so users cannot be verified. Check the token and try again.", 400)
    existing = set()
    with appdb.read() as c:
        for i in range(0, len(ids), 500):
            part = [str(x) for x in ids[i:i + 500]]
            for r in c.execute(f"SELECT telegram_id FROM chats WHERE bot_id=? AND telegram_id IN ({','.join('?' * len(part))})", (bot_id, *part)):
                existing.add(r["telegram_id"])
    todo = [i for i in ids if str(i) not in existing]
    j = _new_job(uid, bot_id, "import", total=len(ids), toVerify=len(todo), imported=0, existing=len(existing),
                 unreachable=0, failed=0, ignored=bad, filename=(filename or "")[:80])
    j["processed"] = len(existing)
    threading.Thread(target=_run_import, args=(j, token, todo), daemon=True).start()
    return _public(j)


def _run_import(j: dict, token: str, todo: list):
    limiter, lock, bot_id = _Limiter(IMPORT_RATE), threading.Lock(), j["botId"]
    batch: list = []

    def flush():
        if not batch:
            return
        rows = batch[:]
        batch.clear()
        with appdb.db() as c:
            c.executemany("INSERT OR IGNORE INTO chats (id,bot_id,telegram_id,name,username,avatar_color,last_active,last_message,"
                          "is_blocked,messages_count,bot_blocked,first_seen) VALUES (?,?,?,?,?,?,?,?,0,0,0,?)", rows)

    def one(tid):
        if j["cancel"]:
            return
        res, err = None, None
        for attempt in range(3):
            limiter.wait()
            try:
                res = tg.call(token, "getChat", {"chat_id": tid}, timeout=15)
                break
            except tg.TgError as e:
                if e.retry_after and attempt < 2:
                    time.sleep(min(e.retry_after, 30))
                    continue
                err = e
                break
        with lock:
            j["processed"] += 1
            if res:
                name = " ".join(x for x in (res.get("first_name"), res.get("last_name")) if x) or res.get("title") or str(tid)
                now = appdb.now_iso()
                batch.append((appdb.new_id("c_", 8), bot_id, str(tid), name[:120], (res.get("username") or "")[:60],
                              _COLORS[tid % len(_COLORS)], now, "Imported", now))
                j["imported"] += 1
                if len(batch) >= 50:
                    flush()
            elif err is not None and err.code in (400, 403, 404) or (err is not None and err.blocked):
                j["unreachable"] += 1
            else:
                j["failed"] += 1

    try:
        with ThreadPoolExecutor(max_workers=6) as ex:
            list(ex.map(one, todo))
        with lock:
            flush()
        with appdb.db() as c:
            n = c.execute("SELECT COUNT(*) n FROM chats WHERE bot_id=? AND is_blocked=0", (bot_id,)).fetchone()["n"]
            c.execute("UPDATE bots SET active_users=?, updated_at=? WHERE id=?", (n, appdb.now_iso(), bot_id))
        j["state"] = "cancelled" if j["cancel"] else "done"
    except Exception as e:  # pragma: no cover
        j["state"], j["error"] = "error", "Import stopped unexpectedly."
    finally:
        j["finishedAt"] = time.time()
        try:
            from backend import connect_bot
            if j["state"] == "done":
                connect_bot.alert(j["uid"], "broadcastStarted",
                                  f"📥 User import finished for {bot_id}: {j['imported']} added, {j['existing']} already there, {j['unreachable']} unreachable.")
        except Exception:
            pass


# ------------------------------------------------------------------ export
FIELDS = {  # key -> (sql column, csv header, json key)
    "id": ("telegram_id", "telegram_id", "id"),
    "name": ("name", "name", "name"),
    "username": ("username", "username", "username"),
    "blocked": ("is_blocked", "blocked", "blocked"),
    "botBlocked": ("bot_blocked", "bot_blocked", "botBlocked"),
    "registeredAt": ("COALESCE(first_seen, last_active)", "registered_at", "registeredAt"),
    "lastActive": ("last_active", "last_active", "lastActive"),
    "lastMessage": ("last_message", "last_message", "lastMessage"),
    "messages": ("messages_count", "messages", "messages"),
    "language": ("language_code", "language", "language"),
}
DEFAULT_FIELDS = ["id", "name", "username", "blocked"]
FILTERS = ("all", "active", "blocked", "active7d", "inactive30d")


def _filter_sql(flt: str):
    if flt == "active":
        return " AND COALESCE(is_blocked,0)=0 AND COALESCE(bot_blocked,0)=0", ()
    if flt == "blocked":
        return " AND (COALESCE(is_blocked,0)=1 OR COALESCE(bot_blocked,0)=1)", ()
    if flt == "active7d":
        return " AND last_active>=?", (appdb.iso_in(days=-7),)
    if flt == "inactive30d":
        return " AND (last_active IS NULL OR last_active<?)", (appdb.iso_in(days=-30),)
    return "", ()


def start_export(uid: str, bot_id: str, fmt: str, fields=None, flt: str = "all", include_dates: bool = False) -> dict:
    own_bot(uid, bot_id)
    fmt = str(fmt).lower()
    fmt = fmt if fmt in ("json", "csv", "txt") else "json"
    flt = flt if flt in FILTERS else "all"
    if isinstance(fields, str):
        fields = [f for f in fields.split(",") if f]
    fields = [f for f in (fields or DEFAULT_FIELDS) if f in FIELDS]
    if include_dates:
        fields += [f for f in ("registeredAt", "lastActive") if f not in fields]
    if "id" not in fields:
        fields.insert(0, "id")
    if fmt == "txt":
        fields = ["id"]
    where, args = _filter_sql(flt)
    with appdb.read() as c:
        total = c.execute("SELECT COUNT(*) n FROM chats WHERE bot_id=?" + where, (bot_id, *args)).fetchone()["n"]
    if not total:
        raise ApiError("There are no users to export for this filter yet.", 400)
    os.makedirs(EXPORT_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(EXPORT_DIR, 0o700)       # exports hold user lists: private to the server user, never world-readable
    except OSError:
        pass
    j = _new_job(uid, bot_id, "export", total=total, format=fmt, fields=fields, filter=flt, includeDates=("registeredAt" in fields), rows=0, size=0,
                 filename=f"users_{bot_id}_{flt}_{time.strftime('%Y%m%d_%H%M%S')}.{fmt}")
    j["path"] = os.path.join(EXPORT_DIR, j["id"] + "." + fmt)
    threading.Thread(target=_run_export, args=(j,), daemon=True).start()
    return _public(j)


def _run_export(j: dict):
    fmt, fields, bot_id = j["format"], j["fields"], j["botId"]
    where, fargs = _filter_sql(j["filter"])
    bools = {"blocked", "botBlocked"}
    try:
        cols = ",".join(FIELDS[f][0] for f in fields)
        with open(os.open(j["path"], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8", newline="") as f, appdb.read() as c:
            cur = c.execute(f"SELECT {cols} FROM chats WHERE bot_id=?{where} ORDER BY rowid", (bot_id, *fargs))
            if fmt == "csv":
                w = csv.writer(f)
                w.writerow([FIELDS[k][1] for k in fields])
            elif fmt == "json":
                f.write("[")
            first = True
            while True:
                rows = cur.fetchmany(20000)
                if not rows:
                    break
                if j["cancel"]:
                    j["state"] = "cancelled"
                    return
                if fmt == "txt":
                    f.write("".join(f"{r[0]}\n" for r in rows))
                elif fmt == "csv":
                    for r in rows:
                        w.writerow([int(bool(v)) if k in bools else ("" if v is None else v) for k, v in zip(fields, r)])
                else:
                    parts = []
                    for r in rows:
                        d = {}
                        for k, v in zip(fields, r):
                            d[FIELDS[k][2]] = (bool(v) if k in bools else (int(v) if k == "id" and str(v).isdigit() else ("" if v is None else v)))
                        parts.append(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
                    f.write(("" if first else ",") + ",".join(parts))
                    first = False
                j["processed"] += len(rows)
                j["rows"] = j["processed"]
            if fmt == "json":
                f.write("]")
        j["size"] = os.path.getsize(j["path"])
        j["state"] = "done"
    except Exception:
        j["state"], j["error"] = "error", "Export failed. Please try again."
    finally:
        j["finishedAt"] = time.time()


def download(uid: str, bot_id: str, jid: str):
    own_bot(uid, bot_id)
    j = get_job(uid, bot_id, jid)
    if j["kind"] != "export" or j["state"] != "done" or not os.path.exists(j["path"]):
        raise ApiError("That export is not ready (or has expired). Start a new export.", 404)
    with open(j["path"], "rb") as f:
        data = f.read()
    mime = {"csv": "text/csv; charset=utf-8", "txt": "text/plain; charset=utf-8"}.get(j["format"], "application/json; charset=utf-8")
    return ("raw", mime, data, {"Content-Disposition": f'attachment; filename="{j["filename"]}"', "Cache-Control": "no-store"})
