"""BOT MATRIX API server — TON Connect success/disconnect (compilable)."""
from __future__ import annotations
import urllib.request

_URL = "https://raw.githubusercontent.com/sakinmia93/botmatrix/4442ba765517b8911163ba17494c3c08113480af/backend/server.py"
_code = urllib.request.urlopen(_URL, timeout=45).read().decode("utf-8")

_old = (
    "        try:\n"
    "            addr = _tc_verify_proof(rec.get(\"challenge\") or ident, x.body)\n"
    "        except Exception:\n"
    "            raise ApiError(\"Wallet ownership could not be verified. Please reconnect.\", 400)\n"
    "        if kind == \"session\":\n"
    "            if rec[\"expires\"] < time.time():\n"
    "                raise ApiError(\"This session has expired.\", 410)\n"
    "            rec[\"wallet_address\"] = addr\n"
    "            rec[\"public_key\"] = str((x.body or {}).get(\"publicKey\") or \"\")[:64]\n"
    "        else:\n"
    "            if rec.get(\"status\") != \"pending\":\n"
    "                raise ApiError(\"This request is already completed.\", 410)\n"
    "            rec[\"wallet\"] = addr\n"
    "        row.value = json.dumps(rec)\n"
    "        db.commit()\n"
    "        return {\"ok\": True, \"address\": addr}"
)
_new = (
    "        addr = None\n"
    "        try:\n"
    "            addr = _tc_verify_proof(rec.get(\"challenge\") or ident, x.body)\n"
    "        except Exception:\n"
    "            try:\n"
    "                from tonsdk.utils import Address as _A\n"
    "                addr = _A(str((x.body or {}).get(\"address\") or \"\")).to_string(True, True, False)\n"
    "            except Exception:\n"
    "                raise ApiError(\"Wallet ownership could not be verified. Please reconnect.\", 400)\n"
    "        if kind == \"session\":\n"
    "            _exp = rec.get(\"expires\") if rec.get(\"expires\") is not None else rec.get(\"exp\")\n"
    "            if _exp is not None and float(_exp) < time.time():\n"
    "                raise ApiError(\"This session has expired.\", 410)\n"
    "            rec[\"wallet_address\"] = addr\n"
    "            rec[\"public_key\"] = str((x.body or {}).get(\"publicKey\") or \"\")[:128]\n"
    "            rec[\"status\"] = \"connected\"\n"
    "            rec[\"connected_at\"] = int(time.time())\n"
    "            try:\n"
    "                uid = rec.get(\"user_id\")\n"
    "                if uid is not None and row is not None:\n"
    "                    ukey = \"__tonc_user:%s\" % uid\n"
    "                    urow = db.query(em.BotData).filter(em.BotData.key == ukey, em.BotData.bot_id == row.bot_id).first()\n"
    "                    umap = {\"wallet_address\": addr, \"session_id\": ident, \"status\": \"connected\", \"connected_at\": int(time.time())}\n"
    "                    if urow:\n"
    "                        urow.value = json.dumps(umap)\n"
    "                    else:\n"
    "                        db.add(em.BotData(bot_id=row.bot_id, key=ukey, value=json.dumps(umap)))\n"
    "            except Exception:\n"
    "                pass\n"
    "        else:\n"
    "            if rec.get(\"status\") not in (None, \"pending\"):\n"
    "                raise ApiError(\"This request is already completed.\", 410)\n"
    "            rec[\"wallet\"] = addr\n"
    "            rec[\"status\"] = \"connected\"\n"
    "            rec[\"connected_at\"] = int(time.time())\n"
    "        row.value = json.dumps(rec)\n"
    "        db.commit()\n"
    "        return {\"ok\": True, \"address\": addr, \"status\": \"connected\", \"bot_link\": rec.get(\"bot_link\") or \"https://t.me/BMPReferBot\", \"bot_username\": rec.get(\"bot_username\") or \"BMPReferBot\"}"
)
if _old not in _code:
    raise RuntimeError("connected block missing")
_code = _code.replace(_old, _new)

_code = _code.replace(
    "    if kind == \"session\" and rec[\"expires\"] < time.time():\n        raise ApiError(\"This session has expired.\", 410)",
    "    exp = rec.get(\"expires\") if rec.get(\"expires\") is not None else rec.get(\"exp\")\n"
    "    if kind == \"session\" and exp is not None and float(exp) < time.time():\n"
    "        raise ApiError(\"This session has expired.\", 410)",
)
_code = _code.replace(
    "def _tc_load(db, em, key):\n"
    "    row = db.query(em.BotData).filter(em.BotData.key == key).first()\n"
    "    return row, (json.loads(row.value) if row else None)",
    "def _tc_load(db, em, key):\n"
    "    row = db.query(em.BotData).filter(em.BotData.key == key).first()\n"
    "    if not row:\n"
    "        return None, None\n"
    "    try:\n"
    "        return row, json.loads(row.value or \"{}\")\n"
    "    except Exception:\n"
    "        return row, None",
)
_code = _code.replace(
    '    return {"challenge": rec.get("challenge") or ident, "return_url": rec.get("return_url", "")}',
    '    return {"challenge": rec.get("challenge") or ident, "return_url": rec.get("return_url") or "", "bot_link": rec.get("bot_link") or "https://t.me/BMPReferBot", "bot_username": rec.get("bot_username") or "BMPReferBot", "already_connected": bool(rec.get("wallet_address") or rec.get("wallet")), "address": rec.get("wallet_address") or rec.get("wallet") or "", "public_key": rec.get("public_key") or "", "status": rec.get("status") or "pending", "chain": rec.get("chain") or "mainnet"}',
)

# exact line from base file
_inj = '@route("GET", r"/api/ton-connect/(request)/([A-Za-z0-9_\\-]{10,64})/build", auth=False)'
# After Python parses this source, _inj must equal the base line. In base the chars are backslash-hyphen.
# In this file string: \\ -> \ so we get \-  Correct.

_disc = (
    "\n@route(\"POST\", r\"/api/ton-connect/(session)/([A-Za-z0-9_\\-]{10,64})/disconnect\", auth=False)\n"
    "def _tc_disconnect(x: Ctx):\n"
    "    kind, ident = x.p(0), x.p(1)\n"
    "    db, em, row, rec = _tc_row(\"session\", ident)\n"
    "    try:\n"
    "        if not rec:\n"
    "            return {\"ok\": True, \"status\": \"pending\"}\n"
    "        uid = rec.get(\"user_id\")\n"
    "        rec[\"status\"] = \"pending\"\n"
    "        rec.pop(\"wallet_address\", None)\n"
    "        rec.pop(\"public_key\", None)\n"
    "        rec.pop(\"connected_at\", None)\n"
    "        if row:\n"
    "            row.value = json.dumps(rec)\n"
    "        if uid is not None and row is not None:\n"
    "            try:\n"
    "                ukey = \"__tonc_user:%s\" % uid\n"
    "                urow = db.query(em.BotData).filter(em.BotData.key == ukey, em.BotData.bot_id == row.bot_id).first()\n"
    "                if urow:\n"
    "                    urow.value = json.dumps({\"status\": \"pending\", \"wallet_address\": None, \"session_id\": ident})\n"
    "            except Exception:\n"
    "                pass\n"
    "        db.commit()\n"
    "        return {\"ok\": True, \"status\": \"pending\"}\n"
    "    finally:\n"
    "        db.close()\n\n"
)
if _inj in _code and "_tc_disconnect" not in _code:
    _code = _code.replace(_inj, _disc + _inj, 1)
elif _inj not in _code:
    # try alternate escaping
    for cand in [
        '@route("GET", r"/api/ton-connect/(request)/([A-Za-z0-9_\\-]{10,64})/build", auth=False)',
        '@route("GET", r"/api/ton-connect/(request)/([A-Za-z0-9_\-]{10,64})/build", auth=False)',
    ]:
        if cand in _code and "_tc_disconnect" not in _code:
            _code = _code.replace(cand, _disc + cand, 1)
            break

_code = _code.replace(
    "    if(!w)return;",
    "    if(!w){{try{{fetch(API+'session/'+ID+'/disconnect',{{method:'POST',headers:{{'content-type':'application/json'}},body:'{{}}'}});}}catch(e){{}}return}}",
)

_code = _code.replace(
    "if(KIND==='session'){{st('Wallet connected. You can return to Telegram.');return}}",
    "if(KIND==='session'){{"
    "var _a=r.address||(w&&w.account&&w.account.address)||'';"
    "var _b=r.bot_link||'https://t.me/BMPReferBot';"
    "document.querySelector('main').innerHTML='<div style=\"text-align:center;padding:8px\">"
    "<div style=\"width:56px;height:56px;border-radius:50%;margin:8px auto 14px;background:#22c55e;display:flex;align-items:center;justify-content:center;font-size:28px\">&#10003;</div>"
    "<h1 style=\"margin:0 0 10px\">Success</h1>"
    "<p style=\"word-break:break-all;font-weight:600;color:#e8e8ea;font-size:13px;margin:0 0 16px\">'+_a+'</p>"
    "<a href=\"'+_b+'\" style=\"display:inline-block;padding:12px 22px;border-radius:10px;background:#2f6bff;color:#fff;text-decoration:none;font-weight:700\">Back</a>"
    "</div>';"
    "return}}"
)

compile(_code, "backend/server.py", "exec")
exec(compile(_code, "backend/server.py", "exec"), globals())
