"""
The TPY (Telebot Python) execution engine.

Design:
  - User code NEVER uses Python's real `import` statement. Instead, safe
    modules (json, re, math, datetime, hashlib, uuid, ...) are PRE-INJECTED
    directly into the execution globals by the runner, exactly like `bot`,
    `message`, `user`, and `libs` are. This avoids the entire class of
    import-based sandbox escapes (no importlib, no __import__, nothing to
    exploit) while still giving user code full access to a wide, useful set
    of standard-library functionality.
  - Any `import` statement written by the user is rejected outright by the
    AST validator below (with one narrow exception kept for readability:
    `from libs import X` is rewritten to just reading `libs.X`, so it is
    also rejected -- users should just use the pre-injected `libs` object).
  - A restricted `__builtins__` dict removes eval/exec/open/getattr/etc.
  - A hard wall-clock timeout is enforced using a worker thread that gets a
    forced SystemExit injected into it if it runs too long.
"""
import ast
import threading
import ctypes
from typing import Any, Dict

from backend.sandbox.safe_builtins import build_safe_builtins, FORBIDDEN_AST_NAMES, FORBIDDEN_ATTR_NAMES, _format_string_is_safe
from backend.sandbox.auto_types import AutoGlobals


class SandboxError(Exception):
    pass


class SandboxTimeout(SandboxError):
    pass


class SandboxSecurityError(SandboxError):
    pass


def _validate_ast(source: str) -> None:
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as e:
        raise SandboxError(f"Syntax error: {e}")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            from backend.sandbox.safe_builtins import import_allowed, SAFE_IMPORTS
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if getattr(node, "level", 0) or not all(import_allowed(m) for m in mods):
                raise SandboxSecurityError(
                    "That import isn't allowed. You can import: " + ", ".join(SAFE_IMPORTS) + ". Libraries like libs.CSV need no import."
                )
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_AST_NAMES:
            raise SandboxSecurityError(f"Use of '{node.id}' is not allowed")
        # Private/dunder attributes are never exposed. This blocks module
        # internals such as random._os, uuid._os, object.__subclasses__, etc.
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in FORBIDDEN_ATTR_NAMES):
            raise SandboxSecurityError(f"Access to private attribute '{node.attr}' is not allowed")
        # `'{0.__class__}'.format(x)` / `.format_map(...)` parse the field spec at RUNTIME from a plain
        # string, so an attribute-access chain hidden in a string literal never shows up as an ast.Attribute
        # node above. Every string literal is checked here instead, regardless of how it is later used.
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and not _format_string_is_safe(node.value):
            raise SandboxSecurityError("A string contains a format field with `.` or `[` (attribute/item access), which is not allowed.")


class _ThreadWithExc(threading.Thread):
    """A thread we can forcefully raise SystemExit inside of, to enforce timeouts."""

    def get_id(self):
        for tid, t in threading._active.items():
            if t is self:
                return tid
        return None

    def raise_exc(self, exctype):
        tid = self.get_id()
        if tid is None:
            return
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), ctypes.py_object(exctype))


def run_sandboxed(source: str, injected_globals: Dict[str, Any], timeout_seconds: int = 20) -> Dict[str, Any]:
    """
    Executes `source` with only `injected_globals` (+ safe builtins + safe
    pre-imported modules) visible. Returns the resulting globals dict, or
    raises SandboxError on failure/timeout.
    """
    _validate_ast(source)

    safe_builtins = build_safe_builtins()
    # AutoGlobals: any undefined CamelCase name becomes a Telegram type factory
    # (LinkPreviewOptions, ReplyParameters, InputRichMessage, …) without
    # shipping a static list that goes stale every Bot API release.
    exec_globals = AutoGlobals()
    exec_globals.update(injected_globals)
    exec_globals["__builtins__"] = safe_builtins
    exec_globals["__name__"] = "tpy_command"

    exception_holder = {}

    def _target():
        try:
            compiled = compile(source, "<command>", "exec")
            exec(compiled, exec_globals)
        except SystemExit:
            pass
        except Exception as e:  # noqa
            exception_holder["error"] = e

    worker = _ThreadWithExc(target=_target, daemon=True)
    worker.start()
    worker.join(timeout=timeout_seconds)

    if worker.is_alive():
        worker.raise_exc(SystemExit)
        worker.join(timeout=2)
        raise SandboxTimeout(f"Command execution exceeded {timeout_seconds} seconds")

    if "error" in exception_holder:
        raise exception_holder["error"]

    return exec_globals
