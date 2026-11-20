"""Unit checks for Request (TBS): Response shape, size cap, redirects, SSRF-on-redirect, background fallback."""
import json, sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, "/home/claude/proj")
from backend.sandbox.libs import request_lib as rl
ok = fail = 0
def check(n, c, x=""):
    global ok, fail
    if c: ok += 1; print("  ✓", n)
    else: fail += 1; print("  ✗", n, x)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/json": b = json.dumps({"a": [1, 2]}).encode(); self.send_response(200); self.send_header("Content-Type", "application/json")
        elif self.path == "/big": b = b"x" * 5000; self.send_response(200)
        elif self.path == "/redir": b = b""; self.send_response(302); self.send_header("Location", "http://169.254.169.254/x")
        elif self.path == "/404": b = b"nope"; self.send_response(404)
        else: b = b"hello"; self.send_response(200)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n)
        b = json.dumps({"got": json.loads(body or b"{}")}).encode(); self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
srv = HTTPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"
real = rl._check_url
rl._check_url = lambda u: (_ for _ in ()).throw(ValueError("URL target is blocked (SSRF protection)")) if "169.254" in u else u
R = rl.RequestModule(1, 5)
r = R.get(base + "/json")
check("status/ok/text/headers/url", r.status_code == 200 and r.ok and r.text.startswith("{") and "Content-Type" in r.headers and r.url.endswith("/json"))
check("json() + dict-style access", r.json() == {"a": [1, 2]} and r["json"]["a"][1] == 2 and r["json"]() == {"a": [1, 2]})
check("content is bytes", isinstance(r.content, bytes))
r = R.get(base + "/404"); check("non-2xx -> ok False, body kept", (not r.ok) and r.status_code == 404 and r.text == "nope")
r = R.post(base + "/p", json={"k": 1}); check("POST json", r.json() == {"got": {"k": 1}})
try: R.get(base + "/big", max_data_size=100); check("max_data_size enforced on bytes", False)
except ValueError as e: check("max_data_size enforced on bytes", "max_data_size" in str(e))
check("big body allowed under default cap", len(R.get(base + "/big").content) == 5000)
try: R.get(base + "/redir"); check("redirect to blocked target refused", False)
except ValueError as e: check("redirect to blocked target refused", "blocked" in str(e))
try: R.get(base + "/x", timeout=300); check("timeout>120 needs fallback_command", False)
except ValueError as e: check("timeout>120 needs fallback_command", "fallback_command" in str(e))
import backend.runtime as rt
calls = []
rt.run_external = lambda bid, trig, upd, options=None: calls.append((bid, trig, options))
t = R.get(base + "/json", timeout=300, fallback_command="/done")
check("background returns task_id + processing", t["status"] == "processing" and t["task_id"])
for _ in range(50):
    if calls: break
    time.sleep(0.1)
check("fallback command receives status/json/status_code", bool(calls) and calls[0][1] == "/done" and calls[0][2]["status"] == "completed" and calls[0][2]["json"] == {"a": [1, 2]} and calls[0][2]["status_code"] == 200 and calls[0][2]["task_id"] == t["task_id"], str(calls))
r = rl.RequestModule(1, 5).get("http://127.0.0.1:1/", timeout=1); check("connection failure -> ok False + error", (not r.ok) and r.get("error"))
print(f"\n{ok} passed, {fail} failed"); sys.exit(1 if fail else 0)
