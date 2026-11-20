"""libs.openai_lib / libs.gemini_lib — AI integrations.

Matches the official TBC docs call surface:
  libs.openai_lib.OpenAIClient(api_key=..., timeout=..., base_url=...)
  libs.openai_lib.AIAssistant(openai_client=..., create_new=True, name=..., ...)
  libs.gemini_lib.GeminiClient(api_key=...)
  libs.gemini_lib.GeminiAIAssistant(gemini_client=..., create_new=True, ...)

The simpler flat helpers from earlier builds (`.chat()`, `.createAssistant()`, ...)
are kept as instance methods on OpenAILib/GeminiLib so existing bot code keeps
working unchanged.
"""
import os
import time
import requests


# ============================================================ error classes
class OpenAIError(Exception):
    """Base exception class for OpenAI errors."""


class OpenAITimeoutError(OpenAIError):
    """Raised when a request to OpenAI/OpenRouter times out."""


class OpenAIAPIError(OpenAIError):
    """Raised when the OpenAI/OpenRouter API returns an error payload."""


class GeminiError(Exception):
    """Base exception class for Gemini errors."""


class GeminiTimeoutError(GeminiError):
    """Raised when a request to Gemini times out."""


class GeminiAPIError(GeminiError):
    """Raised when the Gemini API returns an error payload."""


# ============================================================ OpenAI client
class OpenAIClient:
    """Core client for OpenAI's API (and OpenRouter, via base_url)."""

    def __init__(self, api_key=None, timeout=120, base_url="https://api.openai.com/v1"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        # docs: "extended timeout support up to 160 seconds"
        self.timeout = min(int(timeout or 120), 160)
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    def _headers(self):
        if not self.api_key:
            raise OpenAIError("No API key configured.")
        h = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if "openai.com" in self.base_url:
            h["OpenAI-Beta"] = "assistants=v2"
        return h

    def _post(self, path, json_body):
        try:
            r = requests.post(f"{self.base_url}{path}", headers=self._headers(),
                               json=json_body, timeout=self.timeout)
        except requests.exceptions.Timeout as e:
            raise OpenAITimeoutError(str(e))
        try:
            data = r.json()
        except Exception:
            data = {}
        if not r.ok or "error" in data:
            err = data.get("error")
            msg = err.get("message") if isinstance(err, dict) else err
            raise OpenAIAPIError(msg or f"HTTP {r.status_code}")
        return data

    def _get(self, path):
        try:
            r = requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=self.timeout)
        except requests.exceptions.Timeout as e:
            raise OpenAITimeoutError(str(e))
        try:
            data = r.json()
        except Exception:
            data = {}
        if not r.ok or "error" in data:
            err = data.get("error")
            msg = err.get("message") if isinstance(err, dict) else err
            raise OpenAIAPIError(msg or f"HTTP {r.status_code}")
        return data

    def list_models(self):
        d = self._get("/models")
        out = []
        for m in d.get("data") or d.get("models") or []:
            mid = m.get("id") or m.get("name") or ""
            out.append(mid.split("models/", 1)[-1] if mid.startswith("models/") else mid)
        return sorted(x for x in out if x)

    # ---- chat completions ------------------------------------------------
    def create_chat_completion(self, model="gpt-4o-mini", messages=None, temperature=0.7, **kwargs):
        body = {"model": model, "messages": messages or [], "temperature": temperature, **kwargs}
        return self._post("/chat/completions", body)

    # ---- Assistants API (OpenAI only) ------------------------------------
    def create_assistant(self, name="assistant", instructions="", model="gpt-4o-mini", **kwargs):
        return self._post("/assistants", {"name": name, "instructions": instructions, "model": model, **kwargs})

    def create_thread(self):
        return self._post("/threads", {})

    def create_message(self, thread_id, content, role="user", file_ids=None, **kwargs):
        body = {"role": role, "content": content, **kwargs}
        if file_ids: body["file_ids"] = file_ids
        return self._post(f"/threads/{thread_id}/messages", body)

    def create_run(self, thread_id, assistant_id, model=None, instructions=None, tools=None, timeout=None, **kwargs):
        body = {"assistant_id": assistant_id, **kwargs}
        if model: body["model"] = model
        if instructions: body["instructions"] = instructions
        if tools is not None: body["tools"] = tools
        return self._post(f"/threads/{thread_id}/runs", body)

    def get_run(self, thread_id, run_id):
        try:
            r = requests.get(f"{self.base_url}/threads/{thread_id}/runs/{run_id}",
                              headers=self._headers(), timeout=self.timeout)
            return r.json()
        except Exception as e:
            raise OpenAIAPIError(str(e))

    def list_messages(self, thread_id):
        try:
            r = requests.get(f"{self.base_url}/threads/{thread_id}/messages",
                              headers=self._headers(), timeout=self.timeout)
            return r.json()
        except Exception as e:
            raise OpenAIAPIError(str(e))


    def retrieve_assistant(self, assistant_id):
        r = requests.get(f"{self.base_url}/assistants/{assistant_id}", headers=self._headers(), timeout=self.timeout)
        return r.json()

    def list_assistants(self, limit=20):
        r = requests.get(f"{self.base_url}/assistants", headers=self._headers(),
                         params={"limit": int(limit)}, timeout=self.timeout)
        return r.json()

    def delete_assistant(self, assistant_id):
        r = requests.delete(f"{self.base_url}/assistants/{assistant_id}", headers=self._headers(), timeout=self.timeout)
        try:
            return r.json()
        except Exception:
            return {"id": assistant_id, "deleted": r.ok}

    def retrieve_thread(self, thread_id):
        r = requests.get(f"{self.base_url}/threads/{thread_id}", headers=self._headers(), timeout=self.timeout)
        return r.json()

    def delete_thread(self, thread_id):
        r = requests.delete(f"{self.base_url}/threads/{thread_id}", headers=self._headers(), timeout=self.timeout)
        try:
            return r.json()
        except Exception:
            return {"id": thread_id, "deleted": r.ok}

    def retrieve_message(self, thread_id, message_id):
        r = requests.get(f"{self.base_url}/threads/{thread_id}/messages/{message_id}",
                         headers=self._headers(), timeout=self.timeout)
        return r.json()

    def cancel_run(self, thread_id, run_id):
        return self._post(f"/threads/{thread_id}/runs/{run_id}/cancel", {})

    def poll_run_until_complete(self, thread_id, run_id, check_interval=1.0, max_poll_time=300):
        start = time.time()
        while time.time() - start < float(max_poll_time):
            run = self.get_run(thread_id, run_id)
            status = (run or {}).get("status") if isinstance(run, dict) else None
            if status in ("completed", "failed", "cancelled", "expired", "incomplete"):
                return run
            time.sleep(min(max(float(check_interval), 0.2), 5.0))
        return self.get_run(thread_id, run_id)


class _Content(str):
    """Assistant answer text. Works as plain text (`bot.sendMessage(response["content"])`) and as the Assistants-API block
    list (`response["content"][0]["text"]["value"]`) at the same time."""
    _blocks = None

    def __getitem__(self, i):
        if isinstance(i, int):
            blocks = self._blocks or [{"type": "text", "text": {"value": str(self), "annotations": []}}]
            return blocks[i]
        return str.__getitem__(self, i)


def _content(value):
    if isinstance(value, list):
        text = "".join(((b.get("text") or {}).get("value") or "") if isinstance(b, dict) and isinstance(b.get("text"), dict) else str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in value)
        c = _Content(text)
        c._blocks = value
        return c
    return _Content(value if isinstance(value, str) else str(value))


class AIAssistant:
    """Higher-level wrapper: plain chat if no assistant is configured, or a real
    OpenAI Assistants-API thread when create_new=True / assistant_id is given."""

    def __init__(self, openai_client, create_new=False, name="Assistant",
                 instructions="", model="gpt-4o-mini", assistant_id=None, system_message=None):
        self.client = openai_client
        self.model = model
        self.system_message = system_message or instructions
        self.assistant_id = assistant_id
        self.thread_id = None
        self._history = []
        if create_new and assistant_id is None:
            try:
                res = self.client.create_assistant(name=name, instructions=instructions, model=model)
                self.assistant_id = res.get("id")
            except OpenAIError:
                self.assistant_id = None  # fall back to plain chat mode

    def start_conversation(self):
        if self.assistant_id:
            res = self.client.create_thread()
            self.thread_id = res.get("id")
            return self.thread_id
        self.thread_id = "local-" + str(int(time.time() * 1000))
        self._history = []
        if self.system_message:
            self._history.append({"role": "system", "content": self.system_message})
        return self.thread_id

    def send_message(self, message):
        if not self.thread_id:
            self.start_conversation()
        if self.assistant_id:
            self.client.create_message(self.thread_id, message)
            run = self.client.create_run(self.thread_id, self.assistant_id)
            run_id = run.get("id")
            for _ in range(60):
                status = self.client.get_run(self.thread_id, run_id)
                if status.get("status") in ("completed", "failed", "cancelled", "expired"):
                    break
                time.sleep(1)
            msgs = self.client.list_messages(self.thread_id)
            data = msgs.get("data") or []
            if data:
                first = dict(data[0])
                first["content"] = _content(first.get("content") or [])
                return first
            return {"content": _content([])}
        # plain chat-completion fallback
        self._history.append({"role": "user", "content": message})
        res = self.client.create_chat_completion(model=self.model, messages=self._history)
        content = res["choices"][0]["message"]["content"]
        self._history.append({"role": "assistant", "content": content})
        return {"role": "assistant", "content": _content(content)}

    def get_conversation_history(self, limit=20, thread_id=None):
        tid = thread_id or self.thread_id
        if self.assistant_id and tid:
            try:
                return self.client.list_messages(tid, limit=limit)
            except TypeError:
                return self.client.list_messages(tid)
        hist = list(getattr(self, "_history", []) or [])
        return hist[-int(limit):] if limit else hist


# ==================================================== legacy flat wrapper
class OpenAILib:
    """libs.openai_lib — flat chat-completion helper (kept for backward compat)."""

    # expose the doc-matching classes as attributes so both call styles work:
    #   libs.openai_lib.chat("hi")                       (legacy)
    #   libs.openai_lib.OpenAIClient(api_key=...)         (official TBC docs)
    OpenAIClient = OpenAIClient
    AIAssistant = AIAssistant
    OpenAIError = OpenAIError
    OpenAITimeoutError = OpenAITimeoutError
    OpenAIAPIError = OpenAIAPIError

    def __init__(self, api_key=None):
        self._key = api_key or os.getenv("OPENAI_API_KEY")
        self.api_key = self._key

    def client(self):
        return self

    _PROVIDERS = {
        "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
        "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-4o-mini"),
        "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash"),
    }

    @staticmethod
    def _detect(key):
        k = str(key or "")
        if k.startswith("sk-or-"):
            return "openrouter"
        if k.startswith("AIza"):
            return "gemini"
        return "openai"

    def _provider_client(self, key, provider, timeout=120):
        prov = (provider or self._detect(key)).lower()
        if prov not in self._PROVIDERS:
            raise OpenAIError(f"Unknown provider '{provider}'. Use openai, gemini or openrouter.")
        base, default_model = self._PROVIDERS[prov]
        return OpenAIClient(api_key=key, timeout=timeout, base_url=base), default_model

    def chat(self, key_or_prompt, msg=None, model=None, system=None, temperature=0.7, provider=None, timeout=120, history=None, **kw):
        """libs.openai_lib.chat(key, msg, model=None, system=None, provider="openai"|"gemini"|"openrouter") -> answer text.
        The one-argument form chat("question") uses the key saved on the bot."""
        if msg is None:
            key, prompt = self._key, key_or_prompt
        else:
            key, prompt = key_or_prompt, msg
        if not key:
            raise OpenAIError("No API key. Pass it as the first argument: libs.openai_lib.chat(key, msg).")
        c, default_model = self._provider_client(key, provider, timeout)
        messages = []
        if system:
            messages.append({"role": "system", "content": str(system)})
        messages += list(history or [])
        messages.append({"role": "user", "content": str(prompt)})
        data = c.create_chat_completion(model=model or default_model, messages=messages, temperature=temperature)
        return data["choices"][0]["message"]["content"]

    def models(self, key=None, provider=None, timeout=60):
        """Names of the models the key can use (list of str)."""
        key = key or self._key
        c, _ = self._provider_client(key, provider, timeout)
        return c.list_models()

    def complete(self, prompt, model=None, system=None, temperature=0.7, **kw):
        """TBC-style alias: single-shot completion using the configured key → answer text."""
        return self.chat(prompt, model=model, system=system, temperature=temperature, **kw)

    def assistant(self, *a, **k):
        """TBC-style alias for createAssistant."""
        return self.createAssistant(*a, **k)

    def createAssistant(self, name="assistant", instructions="", model="gpt-4o-mini"):
        try:
            return {"ok": True, "data": OpenAIClient(api_key=self._key).create_assistant(name, instructions, model)}
        except OpenAIError as e:
            return {"ok": False, "error": str(e)}

    def createThread(self):
        try:
            return {"ok": True, "data": OpenAIClient(api_key=self._key).create_thread()}
        except OpenAIError as e:
            return {"ok": False, "error": str(e)}

    def addMessage(self, thread_id, content, role="user"):
        try:
            return {"ok": True, "data": OpenAIClient(api_key=self._key).create_message(thread_id, content, role)}
        except OpenAIError as e:
            return {"ok": False, "error": str(e)}

    def run(self, thread_id, assistant_id):
        try:
            return {"ok": True, "data": OpenAIClient(api_key=self._key).create_run(thread_id, assistant_id)}
        except OpenAIError as e:
            return {"ok": False, "error": str(e)}


# =============================================================== Gemini
class GeminiClient:
    """Core client for Google's Gemini API, OpenAI-compatible surface.

    Docs: every request is capped at a 40-second timeout — any larger value
    passed in is clamped down to 40 seconds.
    """
    MAX_TIMEOUT = 40

    def __init__(self, api_key=None, timeout=40):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.timeout = min(int(timeout or 40), self.MAX_TIMEOUT)

    def _generate(self, model, contents):
        if not self.api_key:
            raise GeminiError("No API key configured.")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={self.api_key}")
        try:
            r = requests.post(url, json={"contents": contents}, timeout=self.timeout)
        except requests.exceptions.Timeout as e:
            raise GeminiTimeoutError(str(e))
        try:
            data = r.json()
        except Exception:
            data = {}
        if not r.ok or "error" in data:
            msg = (data.get("error") or {}).get("message", f"HTTP {r.status_code}")
            raise GeminiAPIError(msg)
        return data

    @staticmethod
    def _messages_to_contents(messages):
        contents = []
        for m in messages or []:
            role = "model" if m.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        return contents

    def create_chat_completion(self, model="gemini-2.0-flash", messages=None, **kwargs):
        contents = self._messages_to_contents(messages)
        data = self._generate(model, contents)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return {"choices": [{"message": {"role": "assistant", "content": text}}], "raw": data}

    def create_assistant(self, name="assistant", instructions="", model="gemini-2.0-flash"):
        return {"id": "gemini-local-assistant", "name": name, "instructions": instructions, "model": model}

    def create_thread(self):
        return {"id": "gemini-thread-" + str(int(time.time() * 1000))}

    def create_message(self, thread_id, content, role="user"):
        return {"ok": True, "thread_id": thread_id, "role": role, "content": content}

    def create_run(self, thread_id, assistant_id):
        return {"id": "gemini-run-" + str(int(time.time() * 1000)), "status": "completed"}


    def retrieve_assistant(self, assistant_id):
        return {"id": assistant_id, "object": "assistant", "note": "Gemini local stub"}

    def list_assistants(self, limit=20):
        return {"data": [], "object": "list"}

    def delete_assistant(self, assistant_id):
        return {"id": assistant_id, "deleted": True}

    def retrieve_thread(self, thread_id):
        return {"id": thread_id, "object": "thread"}

    def delete_thread(self, thread_id):
        return {"id": thread_id, "deleted": True}

    def retrieve_message(self, thread_id, message_id):
        return {"id": message_id, "thread_id": thread_id, "object": "thread.message"}

    def list_messages(self, thread_id, limit=20):
        return {"data": [], "object": "list"}

    def cancel_run(self, thread_id, run_id):
        return {"id": run_id, "status": "cancelled"}

    def poll_run_until_complete(self, thread_id, run_id, check_interval=1.0, max_poll_time=40):
        return {"id": run_id, "status": "completed"}


class GeminiAIAssistant:
    """Higher-level assistant-style wrapper around GeminiClient."""

    def __init__(self, gemini_client, create_new=False, name="Assistant",
                 instructions="", model="gemini-2.0-flash", system_message=None):
        self.client = gemini_client
        self.model = model
        self.system_message = system_message or instructions
        self._history = []
        self.thread_id = None

    def start_conversation(self):
        self.thread_id = self.client.create_thread().get("id")
        self._history = []
        if self.system_message:
            self._history.append({"role": "system", "content": self.system_message})
        return self.thread_id

    def send_message(self, message):
        if not self.thread_id:
            self.start_conversation()
        self._history.append({"role": "user", "content": message})
        res = self.client.create_chat_completion(model=self.model, messages=self._history)
        content = res["choices"][0]["message"]["content"]
        self._history.append({"role": "assistant", "content": content})
        return {"role": "assistant", "content": _content(content)}

    def get_conversation_history(self):
        return list(self._history)


# ==================================================== legacy flat wrapper
class GeminiLib:
    """libs.gemini_lib — flat chat helper (kept for backward compat)."""

    GeminiClient = GeminiClient
    GeminiAIAssistant = GeminiAIAssistant
    GeminiError = GeminiError
    GeminiTimeoutError = GeminiTimeoutError
    GeminiAPIError = GeminiAPIError

    def __init__(self, api_key=None):
        self._key = api_key or os.getenv("GEMINI_API_KEY")

    def chat(self, prompt, model="gemini-1.5-flash"):
        if not self._key:
            raise RuntimeError("No Gemini API key configured. Set it in Bot Settings.")
        c = GeminiClient(api_key=self._key)
        res = c.create_chat_completion(model=model, messages=[{"role": "user", "content": prompt}])
        return res["choices"][0]["message"]["content"]
