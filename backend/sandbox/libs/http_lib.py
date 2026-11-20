import json
import requests as _requests
from urllib.parse import urlparse


def _json_sanitize(obj):
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if hasattr(obj, "_v") and obj.__class__.__name__ in ("_TBCOptionalStr", "_TBCNum"):
        v = obj._v
        if obj.__class__.__name__ == "_TBCOptionalStr":
            return None if v is None else str(v)
        return v
    if isinstance(obj, dict):
        return {str(k): _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_sanitize(v) for v in obj]
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return _json_sanitize(obj.to_dict())
    return str(obj)


def _ip_blocked(ip) -> bool:
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _check_url(url: str):
    """SSRF guard. Platform BASE_URL host is always allowed for webhook broadcast."""
    import ipaddress, socket, os
    u = urlparse(str(url))
    if u.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")
    host = (u.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("URL has no host")
    allowed_hosts = set()
    for envk in ("BASE_URL", "RAILWAY_PUBLIC_DOMAIN", "RAILWAY_STATIC_URL"):
        raw = (os.environ.get(envk) or "").strip()
        if not raw:
            continue
        if "://" not in raw:
            raw = "https://" + raw
        try:
            h = urlparse(raw).hostname
            if h:
                allowed_hosts.add(h.lower().rstrip("."))
        except Exception:
            pass
    if host in allowed_hosts:
        return url
    if host in ("localhost", "metadata.google.internal") or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("URL target is blocked (SSRF protection)")
    if host == "gov" or host.endswith(".gov") or ".gov." in host:
        raise ValueError(".gov domains are not allowed")
    try:
        ips = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            ips = [ipaddress.ip_address(i[4][0]) for i in socket.getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP)]
        except socket.gaierror:
            ips = []
    for ip in ips:
        if _ip_blocked(ip) or str(ip) == "169.254.169.254":
            raise ValueError("URL target is blocked (SSRF protection)")
    return url


def _internal_webhook_post(url, json_body=None, data=None, timeout=60):
    """Run our own /api/new-webhook in-process (correct HMAC + no self-HTTP deadlock).

    Returns immediately when webhook_handler fire-and-forgets the command thread.
    Never performs a real outbound HTTPS call to the same host.
    """
    from urllib.parse import urlparse, parse_qs
    from backend.webhook_handler import handle_webhook
    from backend.errors import ApiError

    class _H:
        def __init__(self):
            self.headers = {"Content-Type": "application/json"}
            self.command = "POST"
        def client_ip(self):
            return "127.0.0.1"

    class _X:
        def __init__(self, query, body_bytes):
            self.query = query
            self.body = {"_raw": body_bytes}
            self.h = _H()

    class _R:
        headers = {"Content-Type": "application/json"}
        encoding = "utf-8"
        def __init__(self, body, status=200, url=""):
            self.url = url
            self.status_code = int(status)
            self.ok = 200 <= self.status_code < 300
            self.reason = "OK" if self.ok else "Error"
            if isinstance(body, tuple) and len(body) >= 3 and body[0] == "raw":
                self._content = body[2] if isinstance(body[2], (bytes, bytearray)) else str(body[2]).encode()
            elif isinstance(body, dict):
                self._content = json.dumps(body).encode()
            else:
                self._content = str(body).encode()
            self.text = self._content.decode("utf-8", "replace")
            self.content = self._content
        def json(self):
            return json.loads(self.text)
        def iter_content(self, chunk_size=65536):
            yield self._content
        def close(self):
            pass

    u = urlparse(str(url))
    q = parse_qs(u.query)
    if json_body is not None:
        raw = json.dumps(json_body, ensure_ascii=False).encode()
    elif data is not None:
        raw = data if isinstance(data, (bytes, bytearray)) else str(data).encode()
    else:
        raw = b""
    try:
        result = handle_webhook(_X(q, raw))
        return _R(result, status=200, url=url)
    except ApiError as e:
        code = int(getattr(e, "status", None) or getattr(e, "code", None) or 400)
        msg = getattr(e, "message", None) or str(e)
        return _R({"ok": False, "error": msg}, status=code, url=url)


MAX_TIMEOUT = 120
MAX_DATA = 52428800


class _JsonField:
    def __init__(self, data):
        self._data = data
    def __call__(self):
        if self._data is not None:
            return self._data
        raise ValueError("Response is not JSON")
    def __str__(self):
        if self._data is None:
            return ""
        try:
            return json.dumps(self._data, ensure_ascii=False)
        except Exception:
            return str(self._data)
    def __repr__(self):
        return self.__str__() or "<no json>"
    def __bool__(self):
        return self._data is not None


class _HTTPResponse:
    def __init__(self, r):
        self._r = r
        self.status_code = r.status_code
        self.ok = r.ok
        self.headers = dict(getattr(r, "headers", {}) or {})
        self.text = r.text
        self.content = r.content
        self.url = getattr(r, "url", "")
        self.reason = getattr(r, "reason", "")
        self.encoding = getattr(r, "encoding", "utf-8")
        try:
            self._json = r.json()
        except Exception:
            self._json = None
        self.body = self._json if self._json is not None else self.text
        self.json = _JsonField(self._json)
    def raise_for_status(self):
        if hasattr(self._r, "raise_for_status"):
            self._r.raise_for_status()
    def __str__(self):
        body = self.text if self._json is None else (json.dumps(self._json, ensure_ascii=False) if not isinstance(self._json, str) else self._json)
        return f"<{self.status_code}> {(body or '')[:3500]}"
    def __repr__(self):
        return self.__str__()
    def __getitem__(self, key):
        if key in ("status_code", "ok", "body", "headers", "text", "json", "content", "url"):
            return getattr(self, key)
        raise KeyError(key)
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


class HTTPLib:
    def __init__(self, default_timeout=60, max_data_size=MAX_DATA, use_proxy=True, ctx=None):
        self.default_timeout = default_timeout
        self.max_data_size = min(int(max_data_size or MAX_DATA), MAX_DATA)
        self._ctx = ctx

    def _do(self, method, url, **kw):
        _check_url(url)
        if kw.get("json") is not None:
            kw["json"] = _json_sanitize(kw["json"])
        timeout = kw.pop("timeout", None)
        timeout = self.default_timeout if timeout is None else timeout
        fallback = kw.pop("fallback_command", None)
        kw.pop("proxies", None)

        # ALWAYS handle our webhook endpoint in-process — never self-HTTP.
        # Real HTTPS to the same Railway service caused ReadTimeout (60s) because
        # the worker waited for handle_webhook while the server was busy.
        try:
            from urllib.parse import urlparse as _up
            _u = _up(str(url))
            _path = (_u.path or "").rstrip("/")
            if method.upper() == "POST" and _path.endswith("/api/new-webhook"):
                r = _internal_webhook_post(
                    url,
                    json_body=kw.get("json"),
                    data=kw.get("data"),
                    timeout=float(timeout),
                )
                return _HTTPResponse(r)
        except Exception as _wh_err:
            class _Fail:
                status_code = 500
                ok = False
                headers = {}
                url = url
                reason = "Internal Webhook Error"
                encoding = "utf-8"
                text = str(_wh_err)
                content = str(_wh_err).encode()
                def json(self):
                    return {"ok": False, "error": str(_wh_err)}
                def iter_content(self, chunk_size=65536):
                    yield self.content
                def close(self):
                    pass
            return _HTTPResponse(_Fail())

        if float(timeout) > MAX_TIMEOUT:
            if not fallback:
                raise ValueError(
                    f"timeout cannot exceed {MAX_TIMEOUT} seconds "
                    f"(pass fallback_command to run it in the background)"
                )
            return self._background(method, url, float(timeout), fallback, kw)
        return self._send(method, url, float(timeout), kw)

    def _send(self, method, url, timeout, kw):
        follow = kw.pop("allow_redirects", True)
        kw.pop("stream", None)
        cur, hops = url, 0
        while True:
            r = _requests.request(method, cur, timeout=timeout, stream=True, allow_redirects=False, **kw)
            loc = r.headers.get("Location")
            if follow and loc and r.status_code in (301, 302, 303, 307, 308) and hops < 5:
                from urllib.parse import urljoin
                cur = urljoin(cur, loc)
                _check_url(cur)
                r.close()
                hops += 1
                if r.status_code in (301, 302, 303) and method.upper() != "HEAD":
                    method, kw = "GET", {k: v for k, v in kw.items() if k not in ("data", "json", "files")}
                continue
            break
        size, chunks = 0, []
        for ch in r.iter_content(65536):
            size += len(ch)
            if size > self.max_data_size:
                r.close()
                raise ValueError("response is larger than the allowed maximum")
            chunks.append(ch)
        r._content = b"".join(chunks)
        r._content_consumed = True
        return _HTTPResponse(r)

    def _background(self, method, url, timeout, fallback, kw):
        import threading, secrets
        task_id = "http_" + secrets.token_hex(6)
        ctx = self._ctx
        def work():
            opts = {"task_id": task_id, "url": url}
            try:
                resp = self._send(method, url, timeout, kw)
                opts.update({"status_code": resp.status_code, "data": resp.text, "json": resp._json, "headers": resp.headers})
            except Exception as e:
                opts.update({"error": str(e), "status_code": 0})
            try:
                if ctx:
                    import datetime
                    from backend.database import SessionLocal
                    from backend.scheduler.scheduler import schedule_task
                    db = SessionLocal()
                    try:
                        schedule_task(db, ctx[0], ctx[1], datetime.datetime.utcnow(), fallback, options=opts, params=None, job_id=None)
                    finally:
                        db.close()
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()
        return {"task_id": task_id, "status": "processing", "message": f"Request is running; the result will be sent to {fallback}"}

    def get(self, url, params=None, headers=None, **kw):
        return self._do("GET", url, params=params, headers=headers, **kw)
    def post(self, url, data=None, json=None, headers=None, **kw):
        return self._do("POST", url, data=data, json=json, headers=headers, **kw)
    def put(self, url, data=None, json=None, headers=None, **kw):
        return self._do("PUT", url, data=data, json=json, headers=headers, **kw)
    def delete(self, url, headers=None, **kw):
        return self._do("DELETE", url, headers=headers, **kw)
    def patch(self, url, data=None, json=None, headers=None, **kw):
        return self._do("PATCH", url, data=data, json=json, headers=headers, **kw)
    def head(self, url, headers=None, **kw):
        return self._do("HEAD", url, headers=headers, **kw)
    def options(self, url, headers=None, **kw):
        return self._do("OPTIONS", url, headers=headers, **kw)
    def request(self, method, url, **kw):
        return self._do(str(method).upper(), url, **kw)
    def __call__(self, *a, **k):
        return self
    def CustomHTTP(self, default_timeout=60, max_data_size=MAX_DATA, use_proxy=True):
        return HTTPLib(default_timeout, max_data_size, use_proxy, self._ctx)
    def close(self):
        return None
