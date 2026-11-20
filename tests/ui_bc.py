import sys, time
sys.path.insert(0, ".")
from ui_lib import *
r = register(f"b{int(time.time())}@x.io", "B")
pw, b = browser(); ctx = b.new_context(viewport={"width": 1366, "height": 1500}); page = ctx.new_page()
page.add_init_script(f"if(!localStorage.getItem('telebot_auth_token')){{localStorage.setItem('telebot_auth_token','{r['token']}');localStorage.setItem('telebot_user',JSON.stringify({json.dumps(r['user'])}));}}")
page.goto(BASE); page.wait_for_timeout(1500)
page.get_by_text("Broadcast Manager", exact=True).first.click(); page.wait_for_timeout(700)
page.get_by_role("button", name="New Broadcast").first.click(); page.wait_for_timeout(700)
page.get_by_role("button", name="Photo", exact=True).click(); page.wait_for_timeout(400)
page.screenshot(path="/tmp/shots/bc_photo.png")
page.locator("button[title^='Use a link']").click(); page.wait_for_timeout(400)
page.screenshot(path="/tmp/shots/bc_url.png")
b.close(); pw.stop()
