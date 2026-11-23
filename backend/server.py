"""BOT MATRIX API server — stable bootstrap (compilable)."""
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
    "        return {\"ok\": True, \"address\": addr, \"status\": \"connected\"}"
)
if _old not in _code:
    raise RuntimeError("connected block missing in base")
_code = _code.replace(_old, _new)

_code = _code.replace(
    '    if kind == "session" and rec["expires"] < time.time():\n        raise ApiError("This session has expired.", 410)',
    '    exp = rec.get("expires") if rec.get("expires") is not None else rec.get("exp")\n'
    '    if kind == "session" and exp is not None and float(exp) < time.time():\n'
    '        raise ApiError("This session has expired.", 410)',
)
_code = _code.replace(
    'def _tc_load(db, em, key):\n'
    '    row = db.query(em.BotData).filter(em.BotData.key == key).first()\n'
    '    return row, (json.loads(row.value) if row else None)',
    'def _tc_load(db, em, key):\n'
    '    row = db.query(em.BotData).filter(em.BotData.key == key).first()\n'
    '    if not row:\n'
    '        return None, None\n'
    '    try:\n'
    '        return row, json.loads(row.value or "{}")\n'
    '    except Exception:\n'
    '        return row, None',
)
_code = _code.replace(
    '    return {"challenge": rec.get("challenge") or ident, "return_url": rec.get("return_url", "")}',
    '    return {"challenge": rec.get("challenge") or ident, "return_url": rec.get("return_url") or "",'
    ' "bot_link": rec.get("bot_link") or "https://t.me/BMPReferBot?start=wallet_ok",'
    ' "bot_username": rec.get("bot_username") or "BMPReferBot",'
    ' "already_connected": bool(rec.get("wallet_address") or rec.get("wallet")),'
    ' "address": rec.get("wallet_address") or rec.get("wallet") or "",'
    ' "public_key": rec.get("public_key") or "", "status": rec.get("status") or "pending",'
    ' "chain": rec.get("chain") or "mainnet"}',
)

# Only simple status text change (valid inside f-string {{ }})
_code = _code.replace(
    "st('Wallet connected. You can return to Telegram.')",
    "st('Wallet connected. Open Telegram and run /checkwallet.')",
)

compile(_code, "backend/server.py", "exec")
exec(compile(_code, "backend/server.py", "exec"), globals())
