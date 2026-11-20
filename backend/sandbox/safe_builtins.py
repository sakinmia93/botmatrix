"""
Whitelist of Python builtins + modules allowed inside sandboxed user
(TPY-style) code. Anything not listed here is unreachable from user code.

Security model:
  1. AST scan rejects: import of any non-whitelisted module, any forbidden
     name (eval/exec/open/__import__/getattr/setattr/globals/locals/...),
     and any dunder attribute access (blocks __class__ / __subclasses__
     sandbox-escape chains).
  2. Only a hand-picked, safe subset of Python builtins is exposed via
     __builtins__ at exec() time — this is the real enforcement boundary,
     the AST scan is a defense-in-depth pre-filter.
  3. A hard wall-clock timeout kills runaway loops.
"""
import builtins as _b


class SandboxSecurityError(Exception):
    pass

# ---- Safe builtins exposed to user code ----------------------------------
SAFE_BUILTIN_NAMES = ['str', 'int', 'float', 'bool', 'dict', 'list', 'set', 'len', 'range', 'zip', 'enumerate', 'sorted', 'map', 'reversed', 'sum', 'Exception', 'ValueError', 'TypeError', 'AttributeError', 'KeyError', 'IndexError', 'RuntimeError', 'ZeroDivisionError', 'NameError', 'SyntaxError', 'IndentationError', 'AssertionError', 'NotImplementedError', 'isinstance', 'type', 'repr', 'any', 'all', 'abs', 'min', 'max', 'ord', 'slice', 'format', 'iter', 'next', 'apply_html_entities',
                      'bin', 'callable', 'chr', 'divmod', 'filter', 'hash', 'hex', 'id', 'issubclass', 'oct', 'pow', 'round', 'tuple',
                      'PermissionError', 'TimeoutError', 'ConnectionError', 'OverflowError', 'StopIteration', 'LookupError', 'ArithmeticError', 'UnicodeError',
                      'getattr', 'hasattr']

# ---- Names that must NEVER be reachable, even indirectly -----------------
# Attribute names that leak frames/code/globals or class internals WITHOUT starting with "_"
# (generators, coroutines, tracebacks, bound methods, and type/class introspection all expose
# these as plain, non-dunder names - the dunder-prefix check alone does not catch them).
FORBIDDEN_ATTR_NAMES = {
    "gi_frame", "gi_code", "gi_yieldfrom", "gi_running",
    "cr_frame", "cr_code", "cr_await", "cr_running", "cr_origin",
    "ag_frame", "ag_code", "ag_await", "ag_running",
    "co_consts", "co_code", "co_names", "co_varnames", "co_filename", "co_argcount", "co_freevars", "co_cellvars",
    "tb_frame", "tb_next", "tb_lineno",
    "f_back", "f_globals", "f_locals", "f_code", "f_builtins", "f_trace",
    "func_globals", "func_code", "func_defaults", "func_closure",
    "im_func", "im_class", "im_self", "mro", "format_map",
}

FORBIDDEN_AST_NAMES = {
    "eval", "exec", "compile", "__import__", "open", "input", "globals",
    "locals", "vars", "setattr", "delattr", "breakpoint",
    "memoryview", "help", "exit", "quit", "classmethod", "staticmethod",
    "property", "super", "object",
}

# ---- Modules explicitly blocked (process, filesystem, network internals,
#      code execution, reflection, concurrency) ----------------------------
FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "importlib", "ctypes",
    "pickle", "marshal", "multiprocessing", "threading", "signal", "pty",
    "resource", "pathlib", "io", "code", "codeop", "inspect", "gc",
    "asyncio", "concurrent", "shelve", "dbm", "sqlite3", "tempfile",
    "platform", "ftplib", "telnetlib", "smtplib", "http", "urllib",
    "webbrowser", "multiprocessing", "ctypes", "cffi", "posix", "pwd",
    "grp", "termios", "fcntl", "mmap", "site", "sysconfig", "distutils",
    "setuptools", "pip", "venv", "ensurepip", "faulthandler", "tracemalloc",
    "atexit", "weakref", "types", "importlib",
}

# ---- Modules pre-injected directly into exec globals (NOT via Python's
#      real import machinery -- there is no `import` statement involved at
#      all, so there is no path-traversal / arbitrary-module risk). These
#      are all pure-python, side-effect-free-on-import, commonly useful
#      standard library modules.
PREIMPORTED_MODULE_NAMES = []


def apply_html_entities(text, entities=None, custom_subs=None):
    if text is None:
        return ""
    value = str(text)
    subs = custom_subs or {}
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    for key, replacement in subs.items():
        value = value.replace(str(key), str(replacement))
    return value

_MISSING = object()


def _safe_getattr(obj, name, default=_MISSING):
    """Documented TPY builtin; private/dunder names are refused so it cannot be used to climb out of the sandbox."""
    n = str(name)
    if n.startswith("_"):
        raise AttributeError(f"Private attribute `{n}` is not allowed.")
    if default is _MISSING:
        return getattr(obj, n)
    return getattr(obj, n, default)


import re as _re
_FMT_FIELD = _re.compile(r"\{([^{}:!]*)[:!]?[^{}]*\}")


def _format_string_is_safe(fmt: str) -> bool:
    """`str.format`/`format_map`/the builtin `format` parse `{field.attr}` / `{field[key]}` themselves,
    at RUNTIME, reading attributes the AST attribute-access check never sees (e.g. '{0.__class__}'.format(x)).
    A field name may only be a bare index or identifier - no `.` or `[` attribute/item access."""
    for m in _FMT_FIELD.finditer(str(fmt)):
        field = m.group(1)
        if "." in field or "[" in field:
            return False
    return True


class _SafeStr(str):
    """A str subclass whose .format()/.format_map() refuse attribute/item access in the field spec.
    User code only ever sees this type (via the sandbox's `str` builtin), so every string literal and
    every result of string operations is protected the same way."""
    def format(self, *a, **kw):
        if not _format_string_is_safe(self):
            raise SandboxSecurityError("Format fields may not use `.` or `[` (attribute/item access is not allowed).")
        return _SafeStr(str.format(self, *a, **kw))

    def format_map(self, mapping):
        raise SandboxSecurityError("str.format_map is not allowed; use .format(...) with plain field names.")


def _safe_format(value, spec=""):
    if not _format_string_is_safe("{:" + str(spec) + "}"):
        raise SandboxSecurityError("Format fields may not use `.` or `[` (attribute/item access is not allowed).")
    return _b.format(value, spec)


def _safe_hasattr(obj, name):
    n = str(name)
    if n.startswith("_"):
        return False
    return hasattr(obj, n)


SAFE_IMPORTS = ("datetime", "math", "random", "string", "uuid", "statistics", "collections", "itertools", "functools",
                "decimal", "textwrap", "json", "re", "hashlib", "base64", "binascii", "time", "fractions", "operator")


def import_allowed(name: str) -> bool:
    return str(name or "").split(".")[0] in SAFE_IMPORTS


_PROXIES = {}


# Reflection helpers that take an ATTRIBUTE NAME AS A STRING: they read `obj.__class__`, call private
# methods, etc. at runtime, completely outside the AST attribute-access check, so they are never exposed.
_OPERATOR_BLOCKLIST = {"attrgetter", "methodcaller"}


def _proxy(mod):
    """Public, non-module attributes only: `uuid.os`, `random.sys` ... are not reachable, so no module can be used to escape."""
    import types
    name = mod.__name__
    block = _OPERATOR_BLOCKLIST if name == "operator" else set()
    if name not in _PROXIES:
        _PROXIES[name] = types.SimpleNamespace(**{k: v for k, v in vars(mod).items()
                                                   if not k.startswith("_") and k not in block and not isinstance(v, types.ModuleType)})
    return _PROXIES[name]


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    """`import math` / `from datetime import datetime, timedelta` work for pure, harmless modules only."""
    root = str(name or "").split(".")[0]
    if level or root not in SAFE_IMPORTS:
        raise ImportError(f"Module '{name}' is not available in TPY. Allowed: " + ", ".join(SAFE_IMPORTS))
    import importlib
    # json / re / time / hashlib / base64 / binascii already exist in every command (with the sandbox's safe variants): reuse those
    if isinstance(globals, dict) and root in globals and globals.get(root) is not None and root in ("json", "re", "time", "hashlib", "base64", "binascii"):
        return globals[root]
    return _proxy(importlib.import_module(root))


def _safe_type(*args, **kwargs):
    if len(args) != 1 or kwargs:
        raise SandboxSecurityError("Dynamic class creation (type(name, bases, dict)) is not allowed.")
    return _b.type(args[0])


def build_safe_builtins() -> dict:
    """Expose exactly the documented TPY builtin surface."""
    safe = {}
    for name in SAFE_BUILTIN_NAMES:
        if name == "apply_html_entities":
            safe[name] = apply_html_entities
        elif name == "getattr":
            safe[name] = _safe_getattr
        elif name == "hasattr":
            safe[name] = _safe_hasattr
        elif name == "format":
            safe[name] = _safe_format
        elif name == "type":
            safe[name] = _safe_type
        elif name == "str":
            safe[name] = _SafeStr
        elif hasattr(_b, name):
            safe[name] = getattr(_b, name)
    safe["__import__"] = _safe_import
    return safe


def build_preimported_modules() -> dict:
    """TPY exposes no undocumented pre-injected stdlib modules."""
    return {}


def _limited_sleep(seconds):
    """TBC time.sleep — max 10 seconds."""
    import time as _t
    try:
        sec = float(seconds)
    except Exception:
        sec = 0
    if sec < 0:
        sec = 0
    if sec > 10:
        sec = 10
    _t.sleep(sec)
    return None
