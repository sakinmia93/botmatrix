"""Redirect-based SSRF: a public URL that redirects to an internal address must be refused."""
import sys, types
sys.path.insert(0, ".")
from backend.sandbox.libs import http_lib
ok = bad = 0
def check(n, c):
    global ok, bad
    print(("  ✓ " if c else "  ✗ ") + n); ok += bool(c); bad += (not c)
class R:
    def __init__(s, code, loc=None): s.status_code, s.headers, s.ok, s.text, s.content, s.url, s.reason, s.encoding = code, ({"Location": loc} if loc else {}), True, "", b"", "u", "", "utf-8"; s._content_consumed = False
    def iter_content(s, n): return iter([b"ok"])
    def close(s): pass
    def json(s): raise ValueError()
calls = []
def fake(method, url, **kw):
    calls.append(url)
    return R(302, "http://127.0.0.1:8080/admin") if "evil" in url else R(302, "http://169.254.169.254/latest/meta-data") if "meta" in url else R(200)
http_lib._requests = types.SimpleNamespace(request=fake)
http_lib._check_url = lambda u, _o=http_lib._check_url: (_ for _ in ()).throw(ValueError("blocked")) if ("127.0.0.1" in u or "169.254" in u) else u
h = http_lib.HTTPLib()
for u in ("http://evil.example/x", "http://meta.example/x"):
    try:
        h._send("GET", u, 5, {}); check("redirect to internal refused: " + u, False)
    except ValueError:
        check("redirect to internal refused: " + u, True)
check("internal address was never requested", not any("127.0.0.1" in c or "169.254" in c for c in calls))
check("normal request still works", h._send("GET", "http://good.example/", 5, {}).status_code == 200)
print(f"{ok} passed, {bad} failed"); sys.exit(1 if bad else 0)
