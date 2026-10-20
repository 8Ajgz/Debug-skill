"""Values of a type the model does not know: opaque, never None unless Optional.

A value annotated with a type outside the model (Path, an ast node, a library class) is
an opaque value. The only uses modelled are passing it on, testing it against None, and
len or a loop over a list of such values. Everything else is rejected.
"""

import pathlib

from src.pyprover.equivalence_verifier import simplify_function, verify_function_equivalence


def _agree(code, f, g, args_list):
    ns = {}
    exec(code, ns)
    for args in args_list:
        assert ns[f](*args) == ns[g](*args), f"{f}{args} differs from {g}{args} in Python"


PATH_SAMPLES = [(pathlib.Path("a"),), (pathlib.Path("b/c"),)]


def test_non_optional_opaque_value_is_never_none():
    code = '''
from pathlib import Path

def f(p: Path):
    return 1 if p is None else 0

def g(p: Path):
    return 0 if p is None or p is not None else 0
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    _agree(code, "f", "g", PATH_SAMPLES)


def test_optional_opaque_value_may_be_none():
    code = '''
from typing import Optional
from pathlib import Path

def f(p: Optional[Path]):
    return 1 if p is None else 0

def g(p: Optional[Path]):
    return 0 if p is None or p is not None else 0
'''
    r = verify_function_equivalence(code, "f", code, "g")
    assert r.equivalent is False
    ns = {}
    exec(code, ns)
    assert ns["f"](None) != ns["g"](None)  # the counterexample is real: Python gives 1 and 0


def test_opaque_value_passed_to_a_helper():
    code = '''
from pathlib import Path

def is_missing(p: Path):
    return p is None

def f(p: Path):
    return 1 if is_missing(p) else 0

def g(p: Path):
    return 0 if p is None or p is not None else 0
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    _agree(code, "f", "g", PATH_SAMPLES)


def test_attribute_of_opaque_value_is_rejected():
    r = simplify_function(
        "from pathlib import Path\n\ndef f(p: Path):\n    return len(p.name) + 0\n", "f")
    assert r.status == "unsupported"
    assert "Any value" in r.reason


def test_returning_opaque_value_is_rejected():
    r = simplify_function("from pathlib import Path\n\ndef f(p: Path):\n    return p\n", "f")
    assert r.status == "unsupported"


def test_list_of_unmodelled_elements_counts_and_loops():
    code = '''
import ast
from typing import List

def f(body: List[ast.stmt]):
    n = 0
    for s in body:
        n = n + 1
    return n

def g(body: List[ast.stmt]):
    return len(body)
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    _agree(code, "f", "g", [([object()] * n,) for n in range(4)])


def test_field_of_unmodelled_type_is_opaque():
    code = '''
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Job:
    root: Path
    n: int

    def f(self):
        return 1 if self.root is None else self.n

    def g(self):
        return self.n
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True


def test_unmodelled_parameter_default_of_none_is_optional():
    code = '''
from pathlib import Path

def f(p: Path = None):
    return 1 if p is None else 0

def h(x: int):
    return f()
'''
    r = verify_function_equivalence(code, "h", code, "h")
    assert r.status in ("decided", "unsupported")  # the call is modelled, and reads the default
