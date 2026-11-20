import sys, time
sys.path.insert(0, "tests")
from ui_lib import *
r = register(f"bt{int(time.time())}@x.io", "B")
pw, b = browser(); ctx = b.new_context(viewport={"width": 1366, "height": 1700}); page = ctx.new_page()
page.add_init_script(f"if(!localStorage.getItem('telebot_auth_token')){{localStorage.setItem('telebot_auth_token','{r['token']}');localStorage.setItem('telebot_user',JSON.stringify({json.dumps(r['user'])}));}}")
page.goto(BASE); page.wait_for_timeout(1500)
page.get_by_text("Broadcast Manager", exact=True).first.click(); page.wait_for_timeout(700)
page.get_by_role("button", name="New Broadcast").first.click(); page.wait_for_timeout(700)
ok = 0
for t, expect in [("Location", "LOCATION DETAILS"), ("Venue", "VENUE DETAILS"), ("Contact", "CONTACT DETAILS"), ("Poll", "Options (one per line"), ("Dice", "DICE DETAILS"), ("Forward", "FORWARD DETAILS")]:
    page.get_by_role("button", name=t, exact=True).click(); page.wait_for_timeout(300)
    good = page.get_by_text(expect, exact=False).count() > 0
    print(("OK  " if good else "FAIL"), t); ok += good
page.get_by_role("button", name="Poll", exact=True).click(); page.screenshot(path="/tmp/shots/bc_poll.png")
page.get_by_role("button", name="Text", exact=True).click(); page.wait_for_timeout(300)
back = page.get_by_text("MESSAGE", exact=True).count() > 0
print(("OK  " if back else "FAIL"), "Text form returns"); ok += back
b.close(); pw.stop(); print(ok, "/ 7"); sys.exit(0 if ok == 7 else 1)
