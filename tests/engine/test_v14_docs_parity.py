import importlib

DOCUMENTED = set(['str', 'int', 'float', 'bool', 'dict', 'list', 'set', 'len', 'range', 'zip', 'enumerate', 'sorted', 'map', 'reversed', 'sum', 'Exception', 'ValueError', 'TypeError', 'AttributeError', 'KeyError', 'IndexError', 'RuntimeError', 'ZeroDivisionError', 'NameError', 'SyntaxError', 'IndentationError', 'AssertionError', 'NotImplementedError', 'isinstance', 'type', 'repr', 'any', 'all', 'abs', 'min', 'max', 'ord', 'slice', 'format', 'iter', 'next', 'apply_html_entities'])

def test_safe_builtin_names_are_exactly_documented():
    mod = importlib.import_module("backend.sandbox.safe_builtins")
    assert set(mod.SAFE_BUILTIN_NAMES) == DOCUMENTED

def test_mdxchange_and_tbcads_are_excluded():
    mod = importlib.import_module("backend.sandbox.libs_namespace")
    names = {n.lower() for n in dir(mod)}
    assert "mdxchange" not in names
    assert "tbcads" not in names

def test_core_library_modules_load():
    for name in (
        "backend.sandbox.libs.resources_lib",
        "backend.sandbox.libs.web3_lib",
    ):
        assert importlib.import_module(name) is not None
