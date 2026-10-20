"""Module flags, static methods, loops over list fields, and isinstance of opaque values.

Each claimed equivalence is checked against Python on the same inputs. A claim that the
model cannot make soundly is checked to stay unsupported.
"""

import pathlib

from src.pyprover.equivalence_verifier import simplify_function, verify_function_equivalence


def _ns(code):
    ns = {}
    exec(code, ns)
    return ns


# --- chunk 2: module flags -------------------------------------------------------

FLAG = '''
try:
    import pyprover_flag_probe_missing_module
    OK = True
except ImportError:
    OK = False
'''


def test_module_flag_is_one_unknown_boolean():
    code = FLAG + '''
def f(x: int):
    return x if OK else x

def g(x: int):
    return x
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True


def test_module_flag_counterexample_is_real():
    code = FLAG + '''
def f(x: int):
    return x if OK else 0

def g(x: int):
    return x
'''
    r = verify_function_equivalence(code, "f", code, "g")
    assert r.equivalent is False
    ns = _ns(code)
    ns["OK"] = False  # the flag is False in this environment, and then the two differ
    assert ns["f"](1) != ns["g"](1)


def test_flag_rebound_by_a_global_statement_is_not_a_flag():
    code = FLAG + '''
def set_ok():
    global OK
    OK = 3

def f(x: int):
    return x if OK else 0
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "neither a parameter nor a local" in r.reason


def test_name_assigned_a_non_boolean_is_not_a_flag():
    code = '''
LIMIT = 3

def f(x: int):
    return x if LIMIT else 0
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"


# --- chunk 4: static methods ---------------------------------------------------

STATIC = '''
class Box:
    n: int

    @staticmethod
    def twice(x):
        return 2 * x

    def via_self(self, x):
        return self.twice(x) + 0

    def via_class(self, x):
        return Box.twice(x) + 0
'''


def test_static_method_called_on_self():
    code = STATIC + '''
def g(x: int):
    return 2 * x
'''
    assert verify_function_equivalence(code, "g", code, "g").equivalent is True
    r = simplify_function(STATIC, "via_self")
    assert r.status in ("simplified", "already_simplest"), r.reason


def test_static_method_called_on_the_class():
    r = simplify_function(STATIC, "via_class")
    assert r.status in ("simplified", "already_simplest"), r.reason
    ns = _ns(STATIC)
    box = ns["Box"]()
    assert box.via_class(3) == box.via_self(3) == 6


def test_static_method_called_on_an_object_is_modelled():
    code = STATIC + '''
def h(b: Box, x: int):
    return b.twice(x)

def g(b: Box, x: int):
    return 2 * x
'''
    assert verify_function_equivalence(code, "h", code, "g").equivalent is True
    _ = _ns(code)


# --- chunk 7: loops over list fields --------------------------------------------

BAG = '''
from typing import List

class Bag:
    items: List[int]

    def sum_by_loop(self):
        s = 0
        for x in self.items:
            s = s + x
        return s

    def sum_by_index(self):
        s = 0
        for i in range(len(self.items)):
            s = s + self.items[i]
        return s

    def weighted(self):
        s = 0
        for i, x in enumerate(self.items):
            s = s + i * x
        return s

    def weighted_by_index(self):
        s = 0
        for i in range(len(self.items)):
            s = s + i * self.items[i]
        return s
'''


def test_loop_over_list_field_matches_index_loop():
    assert verify_function_equivalence(BAG, "sum_by_loop", BAG, "sum_by_index").equivalent is True
    ns = _ns(BAG)
    for items in ([], [4], [1, -2], [3, 0, 7]):
        bag = ns["Bag"]()
        bag.items = items
        assert bag.sum_by_loop() == bag.sum_by_index() == sum(items)


def test_enumerate_over_list_field_matches_index_loop():
    assert verify_function_equivalence(BAG, "weighted", BAG, "weighted_by_index").equivalent is True
    ns = _ns(BAG)
    for items in ([], [4], [1, -2], [3, 0, 7]):
        bag = ns["Bag"]()
        bag.items = items
        assert bag.weighted() == bag.weighted_by_index()


def test_loop_over_a_call_result_is_not_modelled():
    code = '''
def f(text: str):
    n = 0
    for line in text.splitlines():
        n = n + 1
    return n
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"


# --- chunk 8: isinstance of opaque values --------------------------------------

def test_repeated_type_test_of_one_value_agrees():
    code = '''
from pathlib import Path

def f(p: Path):
    return (1 if isinstance(p, str) else 0) + (1 if isinstance(p, str) else 0)

def g(p: Path):
    return 2 * (1 if isinstance(p, str) else 0)
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    for value in (pathlib.Path("a"), "text", None, 3):
        ns = _ns(code)
        assert ns["f"](value) == ns["g"](value)


def test_isinstance_object_holds_for_none_too():
    code = '''
from typing import Optional
from pathlib import Path

def f(p: Optional[Path]):
    return 1 if isinstance(p, object) else 0

def g(p: Optional[Path]):
    return 1 if p is None or p is not None else 1
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    assert _ns(code)["f"](None) == 1


def test_counterexample_from_type_tests_is_not_reported():
    code = '''
from pathlib import Path

def f(p: Path):
    return 1 if isinstance(p, str) else 0

def g(p: Path):
    return 1 if isinstance(p, int) else 0
'''
    r = verify_function_equivalence(code, "f", code, "g")
    assert r.status == "unsupported"
    assert r.equivalent is None
