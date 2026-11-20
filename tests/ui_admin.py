"""UI check: Admin panel is visible to admins only and its tabs load real data."""
import sys
sys.path.insert(0, "tests")
from ui_lib import *
try: register("admin@x.io", "Admin")
except Exception: pass
ok = bad = 0
def check(n, c):
    global ok, bad
    print(("  ✓ " if c else "  ✗ ") + n); ok += bool(c); bad += (not c)
pw, b = browser()
ctx, page, _, errs = login_page(b, "admin@x.io", "password123"); page.wait_for_timeout(2500)
check("admin sees Admin item", page.get_by_text("Admin", exact=True).count() >= 1)
page.get_by_text("Admin", exact=True).first.click(); page.wait_for_timeout(1500)
check("server tab is first: gauges + per-core load", page.get_by_text("Per-core load").count() == 1 and page.get_by_text("Memory").count() >= 1)
def tab(name): page.get_by_role("main").get_by_role("button", name=name, exact=False).first.click(); page.wait_for_timeout(1100)
tab("Overview"); check("overview tiles", page.get_by_text("Users per plan").count() == 1)
for name, probe in (("Bot fleet", "Damage radar"), ("Users", "users"), ("Plans", "Save Matrix Free"), ("Database", "Read-only SQL console"), ("Live logs", "Live"), ("Security", "Security score"), ("Settings", "SMTP password"), ("Tickets", "No tickets")):
    tab(name); check(f"{name} tab loads", page.get_by_text(probe).count() >= 1)
tab("Database"); page.get_by_role("button", name="Run").click(); page.wait_for_timeout(900)
check("SQL console shows rows with masked secrets query", page.get_by_text("rows ·").count() >= 1)
tab("Security"); page.get_by_role("button", name="Scan now").click(); page.wait_for_timeout(2500)
check("security scan runs and lists the sandbox check", page.get_by_text("Code sandbox refuses escape attempts").count() >= 1)
page.get_by_role("button", name="বাংলা").click(); page.wait_for_timeout(500)
check("Bengali toggle translates the panel", page.get_by_text("অ্যাডমিন কন্ট্রোল প্যানেল").count() == 1)
page.get_by_role("button", name="English").click()
page.screenshot(path="/tmp/admin.png")
n = register("user_na@x.io", "Normal")
c2, p2, _, _ = login_page(b, "user_na@x.io", "password123"); p2.wait_for_timeout(2500)
check("normal user has no Admin item", p2.get_by_text("Admin", exact=True).count() == 0)
print(f"{ok} passed, {bad} failed")
