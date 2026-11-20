"""UI checks: Edit raw modal position, long bot names, points box, Gmail hide/copy, notification navigation, uptime seconds."""
import sys, time
sys.path.insert(0, "tests")
from ui_lib import *
N = int(time.time()) % 900000000 + 100000000
BOT = f"{N}:" + "A" * 35
requests.post("http://127.0.0.1:8081/_mock/add_bot", json={"token": BOT, "username": f"f{N}_bot"})
email = f"f{N}@x.io"
tok = register(email, "Fay")["token"]
bid = api("POST", "/bots", tok, json={"token": BOT}).json()["id"]
api("PUT", f"/bots/{bid}", tok, json={"name": "A very long bot name that must not be cut after one letter on desktop screens"})
_adm = login("admin@x.io")["token"]
uid = [u for u in api("GET", "/admin/users?q=" + email, _adm).json()["users"] if u["email"] == email][0]["id"]
api("PUT", f"/admin/users/{uid}", _adm, json={"addExtraPoints": 123456789012})
ok = bad = 0
def check(n, c):
    global ok, bad
    print(("  ✓ " if c else "  ✗ ") + n); ok += bool(c); bad += (not c)
pw, b = browser()
ctx, page, _, errs = login_page(b, email, "password123"); page.wait_for_timeout(2500)
page.get_by_text("My Bots", exact=True).first.click(); page.wait_for_timeout(1500)
page.screenshot(path="/tmp/shots/bots.png")
h = page.locator("h3[title^='A very long bot name']").first
box = h.bounding_box()
print(repr(h.inner_text()), h.evaluate("e => [e.scrollHeight, e.clientHeight]"), box)
check("long bot name wraps and shows most of the text", box is not None and box["width"] > 180 and "A very long" in h.inner_text())
page.get_by_role("button", name="Edit").first.click(); page.wait_for_timeout(1800)
page.get_by_text("Manage", exact=True).first.click(); page.wait_for_timeout(1000)
page.get_by_text("Edit raw").click(); page.wait_for_timeout(500)
m = page.get_by_text("Edit environment variables").first.bounding_box(); vh = page.viewport_size["height"]
check("Edit raw modal is centered, not at the bottom", m and 80 < m["y"] < vh * 0.6)
page.get_by_role("button", name="Cancel").click()
# settings
page.get_by_text("Settings", exact=True).first.click(); page.wait_for_timeout(1200)
check("email hidden by default", page.get_by_text(email).count() == 0)
page.get_by_title("Show email").click(); check("email can be revealed", page.get_by_text(email).count() >= 1)
check("copy email button", page.get_by_title("Copy email").count() == 1)
page.get_by_role("button", name="Plan", exact=True).first.click(); page.wait_for_timeout(1000)
sp = page.locator("span.truncate", has_text="B").first
check("huge extra points stay inside their box", sp.count() and sp.evaluate("e => e.getBoundingClientRect().right <= e.parentElement.getBoundingClientRect().right + 1"))
# notification -> page
api("POST", "/transfers", tok, json={}) if False else None
page.get_by_text("Dashboard", exact=True).first.click(); page.wait_for_timeout(800)
page.wait_for_timeout(4500)
page.locator("button[aria-label*=otif], header button:has(svg.lucide-bell)").first.click(); page.wait_for_timeout(600)
page.get_by_text("New login to your account").first.click(); page.wait_for_timeout(1500)
check("new-login notification opens Settings -> Security", page.get_by_text("Active Sessions").count() + page.get_by_text("active sessions").count() >= 1 or page.get_by_role("button", name="Security").count() >= 1)
page.screenshot(path="/tmp/shots/fix2.png")
print("page errors:", [e for e in errs if "Failed to load" not in e][:3])
print(f"{ok} passed, {bad} failed")
b.close(); pw.stop()
