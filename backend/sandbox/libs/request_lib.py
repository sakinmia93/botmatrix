"""Request - TeleBot Studio HTTP client (global `Request.get/post/put/patch/delete`).

* returns a Response: status_code, text, content, headers, ok, url, json()  (dict-style access still works)
* SSRF guard (http/https only, no internal/reserved targets - also checked on every redirect)
* response size cap: 50 MB (override with max_data_size=...), enforced on the bytes actually read
* timeout default: GET/DELETE 60 s, POST/PUT/PATCH 30 s; above 120 s a fallback_command is required - the call then
  returns {"task_id", "status": "processing"} at once and the result is delivered to that command in `options`
"""
import json as _json
import threading
import uuid

import requests as _requests

from backend.sandbox.libs.http_lib import _check_url, _json_sanitize

MAX_SYNC_TIMEOUT = 120
MAX_DATA_DEFAULT = 50 * 1024 * 1024


class _J:
    """json() result that is also usable directly: Response.json is callable AND behaves like the parsed value."""


def _callable_view(value):
    if isinstance(value, dict):
        class V(dict):
            def __call__(self): return value
        return V(value)
    if isinstance(value, list):
        class L(list):
            def __call__(self): return value
        return L(value)
    return value


class Response(dict):
    def __init__(self, status_code=0, text="", content=b"", headers=None, url="", error=None):
        super().__init__()
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = dict(headers or {})
        self.url = url
        self.ok = 200 <= int(status_code or 0) < 300
        self.error = error
        try:
            self._parsed = _json.loads(text) if text else None
        except Exception:
            self._parsed = None
        self.update({"ok": self.ok, "status_code": status_code, "text": text,
                     "json": _callable_view(self._parsed) if isinstance(self._parsed, (dict, list)) else None,
                     "data": self._parsed if self._parsed is not None else text, "url": url, "headers": self.headers})
        if error:
            self["error"] = error

    def __getattr__(self, k):
        raise AttributeError(k)

    def json(self):                       # noqa: F811 (method form) - dict key "json" keeps the old dict-style access
        if self._parsed is None:
            raise ValueError("response body is not valid JSON")
        return self._parsed

    # attribute `json` must be the method; the dict key stays reachable via r["json"]
    def raise_for_status(self):
        if not self.ok:
            raise _requests.HTTPError(f"{self.status_code} error for {self.url}")


class RequestModule:
    def __init__(self, bot_id=None, user_id=None):
        self._bot_id = bot_id
        self._user_id = user_id

    # ---- public API -----------------------------------------------------------
    def get(self, url, headers=None, timeout=60, fallback_command=None, **kw):
        return self._do("get", url, headers=headers, timeout=timeout, fallback_command=fallback_command, **kw)

    def post(self, url, data=None, json=None, headers=None, timeout=30, fallback_command=None, **kw):
        return self._do("post", url, data=data, json=json, headers=headers, timeout=timeout, fallback_command=fallback_command, **kw)

    def put(self, url, data=None, json=None, headers=None, timeout=30, fallback_command=None, **kw):
        return self._do("put", url, data=data, json=json, headers=headers, timeout=timeout, fallback_command=fallback_command, **kw)

    def patch(self, url, data=None, json=None, headers=None, timeout=30, fallback_command=None, **kw):
        return self._do("patch", url, data=data, json=json, headers=headers, timeout=timeout, fallback_command=fallback_command, **kw)

    def delete(self, url, headers=None, timeout=60, fallback_command=None, **kw):
        return self._do("delete", url, headers=headers, timeout=timeout, fallback_command=fallback_command, **kw)

    # ---- engine -------------------------------------------------------------------
    def _fetch(self, method, url, timeout, max_data, kw):
        s = _requests.Session()
        cur = _check_url(url)
        for _hop in range(6):
            r = s.request(method, cur, timeout=timeout, stream=True, allow_redirects=False,
                          **{k: v for k, v in kw.items() if k in ("headers", "data", "json", "params", "auth", "cookies", "files") and v is not None})
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                from urllib.parse import urljoin
                cur = _check_url(urljoin(cur, r.headers["Location"]))
                if r.status_code in (301, 302, 303):
                    method = "get"
                    kw = {k: v for k, v in kw.items() if k not in ("data", "json", "files")}
                r.close()
                continue
            break
        else:
            raise ValueError("too many redirects")
        buf = bytearray()
        for chunk in r.iter_content(65536):
            buf.extend(chunk)
            if len(buf) > max_data:
                r.close()
                raise ValueError(f"response is larger than max_data_size ({max_data} bytes)")
        r.close()
        enc = r.encoding or "utf-8"
        try:
            text = bytes(buf).decode(enc, errors="replace")
        except Exception:
            text = bytes(buf).decode("utf-8", errors="replace")
        return Response(r.status_code, text, bytes(buf), r.headers, cur)

    def _do(self, method, url, fallback_command=None, timeout=None, **kw):
        kw = {k: (_json_sanitize(v) if k == "json" else v) for k, v in kw.items()}
        max_data = int(kw.pop("max_data_size", None) or MAX_DATA_DEFAULT)
        try:
            timeout = float(timeout if timeout is not None else 30)
        except (TypeError, ValueError):
            raise ValueError("timeout must be a number of seconds")
        _check_url(url)                                   # blocked targets fail immediately, in both modes
        if timeout > MAX_SYNC_TIMEOUT and not fallback_command:
            raise ValueError("timeout above 120 seconds requires fallback_command")
        if fallback_command:
            if timeout > MAX_SYNC_TIMEOUT or kw.pop("background", False):
                return self._background(method, url, timeout, max_data, kw, fallback_command)
        try:
            return self._fetch(method, url, min(timeout, MAX_SYNC_TIMEOUT), max_data, kw)
        except ValueError:
            raise
        except Exception as e:
            return Response(0, "", b"", {}, str(url), error=str(e))

    def _background(self, method, url, timeout, max_data, kw, command):
        if self._bot_id is None:
            raise ValueError("fallback_command needs a running bot context")
        task_id = uuid.uuid4().hex[:16]
        bot_id, uid = self._bot_id, self._user_id

        def work():
            try:
                resp = self._fetch(method, url, min(timeout, 600), max_data, dict(kw))
                opts = {"task_id": task_id, "status": "completed", "status_code": resp.status_code, "text": resp.text,
                        "headers": resp.headers, "ok": resp.ok, "url": resp.url}
                opts["json"] = resp._parsed
            except Exception as e:
                opts = {"task_id": task_id, "status": "failed", "error": str(e), "status_code": 0}
            try:
                from backend import runtime
                update = {"message": {"message_id": 0, "date": 0, "from": {"id": int(uid or 0), "is_bot": False, "first_name": "task"},
                                      "chat": {"id": int(uid or 0), "type": "private"}, "text": str(command)}}
                runtime.run_external(bot_id, str(command), update, options=opts)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()
        return {"ok": True, "task_id": task_id, "status": "processing"}
