"""Admin "server panel": live server vitals, bot fleet / damage radar, slow-response diagnosis, database manager and log tail.

Everything is read from the real machine (/proc, the app database, the event log) - nothing is simulated."""
from __future__ import annotations

import collections
import logging
import os
import re
import shutil
import sqlite3
import statistics
import threading
import time
from typing import Dict, List, Optional

from backend import appdb
from backend.errors import ApiError

log = logging.getLogger("sysmon")
_START = time.time()
_HIST = collections.deque(maxlen=120)           # one sample every 3 s -> last 6 minutes
_lock = threading.Lock()
_prev: Dict[str, object] = {}
_started = False


# ------------------------------------------------------------------ low level readers (Linux /proc, psutil optional)
def _read(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        return ""


def _cpu_times():
    out = {}
    for line in _read("/proc/stat").splitlines():
        if line.startswith("cpu"):
            p = line.split()
            v = [int(x) for x in p[1:9]]
            out[p[0]] = (sum(v), v[3] + v[4])           # total, idle(+iowait)
    return out


def _net_bytes():
    rx = tx = 0
    for line in _read("/proc/net/dev").splitlines()[2:]:
        name, _, rest = line.partition(":")
        if name.strip() == "lo" or not rest:
            continue
        f = rest.split()
        rx += int(f[0]); tx += int(f[8])
    return rx, tx


def _meminfo() -> dict:
    m = {}
    for line in _read("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        try:
            m[k] = int(v.split()[0]) * 1024
        except Exception:
            pass
    return m


def _proc_self() -> dict:
    st = _read("/proc/self/status")
    rss = threads = 0
    for line in st.splitlines():
        if line.startswith("VmRSS:"):
            rss = int(line.split()[1]) * 1024
        elif line.startswith("Threads:"):
            threads = int(line.split()[1])
    try:
        fds = len(os.listdir("/proc/self/fd"))
    except Exception:
        fds = 0
    return {"rss": rss, "threads": threads, "openFiles": fds, "pid": os.getpid()}


def _sample() -> dict:
    now = time.time()
    cur, (rx, tx) = _cpu_times(), _net_bytes()
    cpu, cores = 0.0, []
    pc = _prev.get("cpu")
    if pc:
        for k, (t, i) in cur.items():
            if k in pc:
                dt, di = t - pc[k][0], i - pc[k][1]
                pct = round(100.0 * (dt - di) / dt, 1) if dt > 0 else 0.0
                if k == "cpu":
                    cpu = pct
                else:
                    cores.append(pct)
    rxs = txs = 0.0
    pn = _prev.get("net")
    if pn and now > pn[2]:
        rxs, txs = (rx - pn[0]) / (now - pn[2]), (tx - pn[1]) / (now - pn[2])
    _prev["cpu"], _prev["net"] = cur, (rx, tx, now)
    mi = _meminfo()
    total = mi.get("MemTotal", 0)
    avail = mi.get("MemAvailable", mi.get("MemFree", 0))
    return {"t": int(now), "cpu": cpu, "cores": cores, "memPct": round(100.0 * (total - avail) / total, 1) if total else 0.0,
            "rx": round(rxs), "tx": round(txs)}


def _loop():
    while True:
        try:
            s = _sample()
            with _lock:
                _HIST.append(s)
        except Exception:
            log.exception("sampler")
        time.sleep(3)


def start_sampler() -> None:
    global _started
    if _started:
        return
    _started = True
    try:
        _prev["cpu"], _prev["net"] = _cpu_times(), (*_net_bytes(), time.time())
    except Exception:
        pass
    threading.Thread(target=_loop, daemon=True, name="sysmon").start()


# ------------------------------------------------------------------ vitals
def vitals() -> dict:
    start_sampler()
    with _lock:
        hist = list(_HIST)
    last = hist[-1] if hist else _sample()
    mi = _meminfo()
    total, avail = mi.get("MemTotal", 0), mi.get("MemAvailable", mi.get("MemFree", 0))
    swap_t, swap_f = mi.get("SwapTotal", 0), mi.get("SwapFree", 0)
    try:
        du = shutil.disk_usage(appdb.DB_PATH and os.path.dirname(appdb.DB_PATH) or "/")
        disk = {"total": du.total, "used": du.used, "free": du.free, "pct": round(100.0 * du.used / du.total, 1)}
    except Exception:
        disk = {"total": 0, "used": 0, "free": 0, "pct": 0}
    try:
        la = os.getloadavg()
    except Exception:
        la = (0, 0, 0)
    up = _read("/proc/uptime").split()
    from backend import runtime
    with appdb.read() as c:
        run = appdb.one(c, "SELECT COUNT(*) n FROM bots WHERE status='working'")["n"]
        allb = appdb.one(c, "SELECT COUNT(*) n FROM bots")["n"]
        ev1 = appdb.one(c, "SELECT COUNT(*) n FROM events WHERE kind='command' AND ts>=?", (appdb.iso_in(minutes=-1),))["n"]
        err1 = appdb.one(c, "SELECT COUNT(*) n FROM events WHERE kind='error' AND ts>=?", (appdb.iso_in(hours=-1),))["n"]
    return {"cpu": last["cpu"], "cores": last["cores"], "cpuCount": os.cpu_count() or 1, "load": [round(x, 2) for x in la],
            "mem": {"total": total, "used": total - avail, "available": avail, "cached": mi.get("Cached", 0) + mi.get("Buffers", 0),
                    "pct": last["memPct"], "swapTotal": swap_t, "swapUsed": swap_t - swap_f},
            "disk": disk, "net": {"rxPerSec": last["rx"], "txPerSec": last["tx"]},
            "uptimeSec": int(float(up[0])) if up else int(time.time() - _START), "appUptimeSec": int(time.time() - _START),
            "process": _proc_self(), "python": os.sys.version.split()[0],
            "bots": {"running": run, "total": allb}, "commandsPerMin": ev1, "errorsLastHour": err1,
            "history": hist[-60:]}


# ------------------------------------------------------------------ fleet / damage radar
def speed_class(ms: Optional[float]) -> str:
    if ms is None:
        return "idle"
    if ms < 50:
        return "ultra"
    if ms < 500:
        return "normal"
    if ms < 1500:
        return "slow"
    return "critical"


def fleet(hours: int = 24) -> dict:
    hours = max(1, min(int(hours or 24), 24 * 30))
    since = appdb.iso_in(hours=-hours)
    with appdb.read() as c:
        bots = appdb.rows(c, "SELECT b.id,b.name,b.username,b.status,b.user_id,b.total_commands,u.email,"
                             "(SELECT COUNT(*) FROM chats c WHERE c.bot_id=b.id) audience FROM bots b LEFT JOIN users u ON u.id=b.user_id")
        ev = appdb.rows(c, "SELECT bot_id,kind,ms,cmd FROM events WHERE ts>=? AND kind IN ('command','error')", (since,))
    per: Dict[str, dict] = {}
    for e in ev:
        d = per.setdefault(e["bot_id"], {"n": 0, "err": 0, "ms": [], "cmds": collections.Counter(), "cmd_ms": collections.defaultdict(list)})
        if e["kind"] == "error":
            d["err"] += 1
            continue
        d["n"] += 1
        if e["ms"] is not None:
            d["ms"].append(e["ms"])
            if e["cmd"]:
                d["cmd_ms"][e["cmd"]].append(e["ms"])
        if e["cmd"]:
            d["cmds"][e["cmd"]] += 1
    total_busy = sum(sum(d["ms"]) for d in per.values()) or 1
    total_n = sum(d["n"] for d in per.values()) or 1
    rows = []
    for b in bots:
        d = per.get(b["id"]) or {"n": 0, "err": 0, "ms": [], "cmds": collections.Counter(), "cmd_ms": {}}
        ms = sorted(d["ms"])
        avg = round(sum(ms) / len(ms), 1) if ms else None
        p95 = ms[min(len(ms) - 1, int(len(ms) * 0.95))] if ms else None
        busy = sum(ms)
        er = round(100.0 * d["err"] / max(1, d["n"] + d["err"]), 1) if (d["n"] or d["err"]) else 0.0
        share = round(100.0 * busy / total_busy, 1)
        flags = []
        if share >= 40 and len(per) > 1:
            flags.append("heavy-load")
        if er >= 20 and d["n"] + d["err"] >= 5:
            flags.append("high-errors")
        if avg is not None and avg >= 1500:
            flags.append("critical-slow")
        elif avg is not None and avg >= 500:
            flags.append("slow")
        if d["n"] / hours > 600:
            flags.append("flooding")
        top = []
        for cmd, n in d["cmds"].most_common(3):
            cm = d["cmd_ms"].get(cmd) or []
            top.append({"cmd": cmd, "runs": n, "avgMs": round(sum(cm) / len(cm), 1) if cm else None})
        rows.append({"id": b["id"], "name": b["name"], "username": b["username"], "owner": b["email"] or "", "ownerId": b["user_id"],
                     "status": b["status"], "audience": b["audience"] or 0, "commands": b["total_commands"] or 0,
                     "runs": d["n"], "errors": d["err"], "errorRate": er, "avgMs": avg, "p95Ms": p95, "busyMs": busy,
                     "loadShare": share, "runShare": round(100.0 * d["n"] / total_n, 1), "speed": speed_class(avg), "flags": flags, "top": top})
    rows.sort(key=lambda r: (-r["busyMs"], -r["runs"]))
    cats = collections.Counter(r["speed"] for r in rows)
    return {"hours": hours, "bots": rows, "speedCounts": dict(cats),
            "damaging": [r for r in rows if r["flags"] and r["status"] == "working"][:20]}


_SLOW_PATTERNS = [
    (r"time\.sleep\s*\(", "The code calls time.sleep(): every sleep holds the whole command (and the user's reply) for that long."),
    (r"\bHTTP\.(get|post|put|delete|request)\b|requests\.|customHTTP", "It makes outside HTTP requests inside the command; a slow remote server slows the reply."),
    (r"\bfor\b[^\n]*\bin\b[^\n]*\bgetAllData|getAllData\s*\(", "It loads ALL stored data in a loop/command; with many records this is heavy. Use getData(key) instead."),
    (r"\bBot\.broadcast\b|\bsendBroadcast\b", "It starts broadcasts from a command; the test-run + queueing adds latency."),
    (r"\bwhile\s+True\b|\bwhile\s+1\b", "A `while True` loop was found; make sure it always exits."),
    (r"libs\.(openai_lib|gemini_lib|translate)", "AI / translation libraries are called synchronously; those calls take seconds."),
    (r"libs\.(TonLib|web3lib)", "Blockchain RPC calls are made inside the command; network latency of the node adds up."),
    (r"libs\.(OpenCV|Pillow)", "Image processing runs in the command, which is CPU heavy."),
]


def diagnose(bot_id: str, hours: int = 24) -> dict:
    f = fleet(hours)
    r = next((x for x in f["bots"] if x["id"] == bot_id), None)
    if not r:
        raise ApiError("Bot not found.", 404)
    with appdb.read() as c:
        b = appdb.one(c, "SELECT commands_json FROM bots WHERE id=?", (bot_id,))
        errs = appdb.rows(c, "SELECT cmd,COUNT(*) n FROM events WHERE bot_id=? AND kind='error' AND ts>=? GROUP BY cmd ORDER BY n DESC LIMIT 5",
                          (bot_id, appdb.iso_in(hours=-hours)))
        wait = appdb.one(c, "SELECT COUNT(*) n FROM broadcasts WHERE status IN ('Active','Paused') AND target_bot_ids LIKE ?", (f"%{bot_id}%",))["n"]
    reasons: List[dict] = []
    if r["avgMs"] is not None and r["avgMs"] >= 500:
        slow = sorted([t for t in r["top"] if t["avgMs"]], key=lambda t: -t["avgMs"])
        if slow:
            reasons.append({"level": "warn", "text": f"Average response is {r['avgMs']:.0f} ms. Slowest busy command: {slow[0]['cmd']} ({slow[0]['avgMs']:.0f} ms avg over {slow[0]['runs']} runs)."})
    if r["p95Ms"] and r["avgMs"] and r["p95Ms"] > 4 * max(1, r["avgMs"]):
        reasons.append({"level": "info", "text": f"p95 is {r['p95Ms']} ms vs {r['avgMs']:.0f} ms average: a few very slow runs (an outside service or a Telegram rate limit?)."})
    if r["errorRate"] >= 10:
        worst = ", ".join(f"{e['cmd']} x{e['n']}" for e in errs if e["cmd"]) or "see Errors tab"
        reasons.append({"level": "bad", "text": f"{r['errorRate']}% of runs fail ({worst}). Failing runs often retry or wait on timeouts."})
    if wait:
        reasons.append({"level": "info", "text": f"{wait} broadcast(s) are running for this bot; they share Telegram's per-bot rate limit (about 30 msgs/s) with normal replies, so replies can queue behind them."})
    if r["loadShare"] >= 40:
        reasons.append({"level": "bad", "text": f"This bot uses {r['loadShare']}% of all execution time on the server."})
    if "flooding" in r["flags"]:
        reasons.append({"level": "bad", "text": "More than 600 commands per hour are being run; check for loops, spam or an abusive user."})
    hits = set()
    for cm in appdb.jload(b["commands_json"], []) if b else []:
        code = cm.get("code") or ""
        for pat, why in _SLOW_PATTERNS:
            if re.search(pat, code) and why not in hits:
                hits.add(why)
                reasons.append({"level": "info", "text": f"/{str(cm.get('name') or '').lstrip('/')}: {why}"})
    v = vitals()
    if v["cpu"] >= 85:
        reasons.append({"level": "bad", "text": f"The server CPU is at {v['cpu']}% - every bot is slower right now."})
    if v["mem"]["pct"] >= 90:
        reasons.append({"level": "bad", "text": f"Server memory is {v['mem']['pct']}% used; swapping makes everything slow."})
    if not reasons:
        reasons.append({"level": "ok", "text": "No problem found. This bot is responding normally."})
    return {"bot": r, "reasons": reasons}


def bot_action(bot_id: str, action: str) -> dict:
    from backend import runtime
    with appdb.read() as c:
        b = appdb.one(c, "SELECT id,name,user_id,status FROM bots WHERE id=?", (bot_id,))
    if not b:
        raise ApiError("Bot not found.", 404)
    if action == "stop":
        res = runtime.set_running(bot_id, False)
    elif action == "start":
        res = runtime.set_running(bot_id, True)
    elif action == "restart":
        runtime.set_running(bot_id, False)
        res = runtime.set_running(bot_id, True)
    else:
        raise ApiError("Unknown action.", 400)
    if action in ("stop", "restart"):
        appdb.notify(b["user_id"], "Bot " + ("restarted" if action == "restart" else "stopped") + " by an administrator",
                     f"“{b['name']}” was {action}ed by the platform administrator" + (" because it was using too many resources." if action == "stop" else "."),
                     "warning", "bot:" + bot_id)
    return {"success": bool(res.get("ok", True)), "error": res.get("error")}


# ------------------------------------------------------------------ logs (in-memory ring buffer of everything the server logs)
class _Ring(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.buf = collections.deque(maxlen=2000)
        self.n = 0

    def emit(self, record):
        try:
            from backend import error_clean
            msg = error_clean.redact(record.getMessage())
            if record.exc_info:
                msg += " | " + error_clean.redact(str(record.exc_info[1]))
            self.n += 1
            self.buf.append({"i": self.n, "t": time.strftime("%H:%M:%S", time.localtime(record.created)), "level": record.levelname,
                             "src": record.name, "msg": msg[:600]})
        except Exception:
            pass


_ring: Optional[_Ring] = None


def install_log_buffer() -> None:
    global _ring
    if _ring is None:
        _ring = _Ring()
        logging.getLogger().addHandler(_ring)


def logs(level: str = "ALL", q: str = "", after: int = 0, limit: int = 300) -> dict:
    install_log_buffer()
    order = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}
    lo = order.get(level.upper(), -1)
    q = (q or "").lower()
    out = [r for r in list(_ring.buf) if r["i"] > after and order.get(r["level"], 0) >= lo and (not q or q in r["msg"].lower() or q in r["src"].lower())]
    return {"lines": out[-max(1, min(limit, 1000)):], "last": _ring.n}


# ------------------------------------------------------------------ database manager
def _dbs() -> Dict[str, str]:
    paths = {"app": appdb.DB_PATH}
    try:
        from backend.config import DATABASE_URL
        if DATABASE_URL.startswith("sqlite:///"):
            paths["engine"] = DATABASE_URL[len("sqlite:///"):]
    except Exception:
        pass
    return {k: v for k, v in paths.items() if v}


def _size(p: str) -> int:
    try:
        return os.path.getsize(p)
    except Exception:
        return 0


def db_info() -> dict:
    out = {}
    for name, path in _dbs().items():
        info = {"path": os.path.basename(path), "size": _size(path), "wal": _size(path + "-wal"), "shm": _size(path + "-shm"), "tables": []}
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
                try:
                    n = conn.execute(f'SELECT COUNT(*) FROM "{t["name"]}"').fetchone()[0]
                except Exception:
                    n = None
                info["tables"].append({"name": t["name"], "rows": n})
            info["pages"] = conn.execute("PRAGMA page_count").fetchone()[0]
            info["free"] = conn.execute("PRAGMA freelist_count").fetchone()[0]
            info["pageSize"] = conn.execute("PRAGMA page_size").fetchone()[0]
            info["journal"] = conn.execute("PRAGMA journal_mode").fetchone()[0]
            info["fragmentationPct"] = round(100.0 * info["free"] / info["pages"], 1) if info["pages"] else 0
            conn.close()
        except Exception as e:
            info["error"] = str(e)[:120]
        out[name] = info
    out["backups"] = [{"name": f, "size": _size(os.path.join(_backup_dir(), f))} for f in sorted(os.listdir(_backup_dir()))[-10:]] if os.path.isdir(_backup_dir()) else []
    return out


def _backup_dir() -> str:
    return os.path.join(os.path.dirname(appdb.DB_PATH), "backups")


def db_action(action: str, which: str = "app") -> dict:
    paths = _dbs()
    if which not in paths:
        raise ApiError("Unknown database.", 400)
    path = paths[which]
    if action == "integrity":
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        res = [r[0] for r in conn.execute("PRAGMA integrity_check")]
        conn.close()
        return {"success": res == ["ok"], "result": res[:20]}
    if action == "vacuum":
        before = _size(path)
        conn = sqlite3.connect(path, timeout=30)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
        conn.close()
        return {"success": True, "before": before, "after": _size(path)}
    if action == "checkpoint":
        conn = sqlite3.connect(path, timeout=30)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        return {"success": True, "wal": _size(path + "-wal")}
    if action == "optimize":
        conn = sqlite3.connect(path, timeout=30)
        conn.execute("PRAGMA optimize")
        conn.execute("ANALYZE")
        conn.close()
        return {"success": True}
    if action == "backup":
        os.makedirs(_backup_dir(), exist_ok=True)
        os.chmod(_backup_dir(), 0o700)
        name = f"{which}-{time.strftime('%Y%m%d-%H%M%S')}.db"
        dst = os.path.join(_backup_dir(), name)
        src = sqlite3.connect(path, timeout=30)
        d = sqlite3.connect(dst)
        src.backup(d)
        d.close(); src.close()
        os.chmod(dst, 0o600)
        old = sorted(os.listdir(_backup_dir()))[:-10]
        for f in old:                                   # keep the 10 newest snapshots
            try:
                os.remove(os.path.join(_backup_dir(), f))
            except OSError:
                pass
        return {"success": True, "name": name, "size": _size(dst)}
    raise ApiError("Unknown action.", 400)


_SECRET_COLS = re.compile(r"token|password|hash|secret|api_key|code|private|mnemonic|seed|env_vars|commands_json", re.I)


def sql_readonly(query: str, which: str = "app", limit: int = 200) -> dict:
    """SELECT-only console. Uses SQLite's authorizer so nothing can write, attach or load extensions; secret columns are masked."""
    q = (query or "").strip().rstrip(";")
    if not q or ";" in q or not re.match(r"^(select|with|explain|pragma\s+(table_info|index_list|foreign_key_list|page_count))\b", q, re.I):
        raise ApiError("Only a single SELECT query is allowed here.", 400)
    paths = _dbs()
    if which not in paths:
        raise ApiError("Unknown database.", 400)
    conn = sqlite3.connect(f"file:{paths[which]}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    OK = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}

    def auth(action, a1, a2, db, src):
        if action in OK:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_PRAGMA and a1 in ("table_info", "index_list", "foreign_key_list", "page_count"):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    conn.set_authorizer(auth)
    t0 = time.time()
    try:
        cur = conn.execute(q)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(max(1, min(limit, 500)))
    except sqlite3.Error as e:
        raise ApiError("SQL error: " + str(e)[:200], 400)
    finally:
        conn.close()
    masked = [bool(_SECRET_COLS.search(c)) for c in cols]
    data = [["••••••••" if (masked[i] and v not in (None, "")) else (v if isinstance(v, (int, float, type(None))) else str(v)[:300]) for i, v in enumerate(r)] for r in rows]
    return {"columns": cols, "rows": data, "ms": round((time.time() - t0) * 1000, 1), "truncated": len(rows) >= limit}
