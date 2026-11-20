"""Tiny fake Telegram Bot API for offline tests.  python tests/mock_telegram.py [port]"""
import json, sys, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
BOTS = {}      # token -> {"id":int,"username":str,"first_name":str}
QUEUES = {}    # token -> list of updates
SENT = []      # {"token","method","params"}
UID = [100]


def add_bot(token, username=None):
    bid = int(token.split(":")[0])
    BOTS[token] = {"id": bid, "is_bot": True, "username": username or f"bot{bid}_bot", "first_name": f"Bot {bid}"}
    QUEUES.setdefault(token, [])


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a): pass

    def _out(self, obj, code=200, raw=None, ctype="application/json"):
        b = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if not raw: return {}
        ct = self.headers.get("Content-Type", "")
        if ct.startswith("multipart/"):
            import email
            msg = email.message_from_bytes(b"Content-Type: " + ct.encode() + b"\r\n\r\n" + raw)
            d = {}
            for part in msg.get_payload():
                nm = part.get_param("name", header="content-disposition")
                if part.get_filename():
                    d[nm] = "__uploaded__:" + part.get_filename() + ":" + str(len(part.get_payload(decode=True) or b""))
                else:
                    v = (part.get_payload(decode=True) or b"").decode(errors="ignore")
                    try: d[nm] = json.loads(v) if v[:1] in "{[" else v
                    except Exception: d[nm] = v
            return d
        if "json" in ct:
            try: return json.loads(raw)
            except Exception: return {}
        d = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode(errors="ignore")).items()}
        for k, v in list(d.items()):
            try: d[k] = json.loads(v) if v[:1] in "{[" else v
            except Exception: pass
        return d

    def do_GET(self):
        if self.path.startswith("/_mock/sent"):
            with LOCK: return self._out(SENT)
        if "/file/bot" in self.path:
            return self._out(None, raw=b"\xff\xd8\xff\xe0fakejpeg", ctype="image/jpeg")
        self._out({"ok": False}, 404)

    def do_POST(self):
        body = self._body()
        p = self.path
        if p.startswith("/turnstile"):
            return self._out({"success": body.get("response") == "good-token" and body.get("secret") == "sek"})
        if p.startswith("/_mock/push"):
            tok = body["token"]; upd = body["update"]
            with LOCK:
                UID[0] += 1; upd["update_id"] = UID[0]; QUEUES.setdefault(tok, []).append(upd)
            return self._out({"ok": True})
        if p.startswith("/_mock/add_bot"):
            add_bot(body["token"], body.get("username")); return self._out({"ok": True})
        if p.startswith("/_mock/fail"):
            FAIL.update(body); return self._out({"ok": True})
        if not p.startswith("/bot"):
            return self._out({"ok": False}, 404)
        tok, _, method = p[4:].partition("/"); method = method[:1].lower() + method[1:]
        if tok not in BOTS or tok in FAIL.get("revoked", []):
            return self._out({"ok": False, "error_code": 401, "description": "Unauthorized"}, 401)
        if method == "getMe": return self._out({"ok": True, "result": BOTS[tok]})
        if method == "getUpdates":
            off = int(body.get("offset") or 0); wait = min(int(body.get("timeout") or 0), 3); end = time.time() + wait
            while True:
                with LOCK:
                    ups = [u for u in QUEUES.get(tok, []) if u["update_id"] >= off]
                    QUEUES[tok] = ups
                if ups or time.time() >= end: break
                time.sleep(0.1)
            return self._out({"ok": True, "result": ups})
        if method == "answerCallbackQuery":
            with LOCK: SENT.append({"method": method, "token": tok, "params": body})
        if method in ("deleteWebhook", "answerCallbackQuery", "setMyCommands", "sendChatAction"): return self._out({"ok": True, "result": True})
        if method == "getUserProfilePhotos":
            return self._out({"ok": True, "result": {"total_count": 1, "photos": [[{"file_id": "F1", "width": 100, "height": 100}]]}})
        if method == "getChat":
            c = str(body.get("chat_id"))
            if c in FAIL.get("unreachable", []) or not c.lstrip("-").isdigit() or int(c) <= 0:
                return self._out({"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}, 400)
            return self._out({"ok": True, "result": {"id": int(c), "type": "private", "first_name": "User" + c, "last_name": "Imported", "username": "u" + c}})
        if method == "getFile": return self._out({"ok": True, "result": {"file_id": "F1", "file_path": "photos/p.jpg"}})
        if method in ("createInvoiceLink", "sendInvoice"):
            # Mirrors real Telegram: the wire field is literally called "payload" (not
            # "invoice_payload" -- that's only TBC's friendlier doc name for it).
            for req in ("title", "description", "payload", "currency", "prices"):
                if not body.get(req) and body.get(req) != 0:
                    return self._out({"ok": False, "error_code": 400, "description": f'Bad Request: parameter "{req}" is required'}, 400)
            with LOCK: SENT.append({"token": tok, "method": method, "params": body})
            if method == "createInvoiceLink":
                return self._out({"ok": True, "result": "https://t.me/$mockinvoice"})
            cid = body.get("chat_id")
            res = {"message_id": len(SENT), "date": int(time.time()), "chat": {"id": cid}, "invoice": {"title": body["title"], "description": body["description"]}}
            return self._out({"ok": True, "result": res})
        cid = body.get("chat_id")
        if str(cid) in FAIL.get("blocked", []):
            return self._out({"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"}, 403)
        if str(cid) in FAIL.get("error", []):
            return self._out({"ok": False, "error_code": 400, "description": "Bad Request: can't parse entities: Unsupported start tag"}, 400)
        with LOCK: SENT.append({"token": tok, "method": method, "params": body})
        res = {"message_id": len(SENT), "date": int(time.time()), "chat": {"id": cid}, "text": body.get("text", "")}
        for fld in ("photo", "video", "audio", "document", "animation", "voice", "video_note", "sticker"):
            if str(body.get(fld, "")).startswith("__uploaded__"):
                res[fld] = [{"file_id": "FID_" + tok[:4], "width": 1, "height": 1}] if fld == "photo" else {"file_id": "FID_" + tok[:4]}
        return self._out({"ok": True, "result": res})


FAIL = {}

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
