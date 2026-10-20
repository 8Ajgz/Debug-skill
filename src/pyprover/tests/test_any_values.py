"""Any values: opaque, passed on unchanged, None-tested, and measured by len and membership.

An Any value is any Python object, so nothing about it is known except whether it is None.
The model therefore accepts only the uses that do not depend on what the object is. Each
claimed equivalence is checked against Python on real values, including None.
"""

from src.pyprover.equivalence_verifier import simplify_function, verify_function_equivalence

SAMPLES = [None, 0, 1, "x", [], {"k": 1}]


def _ns(code):
    ns = {}
    exec(code, ns)
    return ns


def _agree(code, f, g, args_list):
    ns = _ns(code)
    for args in args_list:
        assert ns[f](*args) == ns[g](*args), f"{f}{args} differs from {g}{args} in Python"


class TestNoneTests:

    def test_none_test_on_any_is_modelled(self):
        code = '''
from typing import Any

def f(x: int, a: Any):
    return x if a is None else x

def g(x: int, a: Any):
    return x if a is None or a is not None else x
'''
        assert verify_function_equivalence(code, "f", code, "g").equivalent is True
        _agree(code, "f", "g", [(x, a) for x in range(-2, 3) for a in SAMPLES])

    def test_not_none_test_distinguishes_none_from_other_values(self):
        code = '''
from typing import Any

def f(a: Any):
    return 1 if a is not None else 0

def g(a: Any):
    return 0 if a is None else 1
'''
        assert verify_function_equivalence(code, "f", code, "g").equivalent is True
        _agree(code, "f", "g", [(a,) for a in SAMPLES])

    def test_different_none_tests_are_not_equivalent(self):
        code = '''
from typing import Any

def f(a: Any):
    return 1 if a is None else 0

def g(a: Any):
    return 0 if a is None or a is not None else 0
'''
        assert verify_function_equivalence(code, "f", code, "g").equivalent is False


class TestPassedOn:

    def test_any_passed_to_a_helper_that_none_tests_it(self):
        code = '''
from typing import Any

def is_missing(a: Any):
    return a is None

def f(a: Any):
    return 1 if is_missing(a) else 0

def g(a: Any):
    return 1 if a is None else 0
'''
        assert verify_function_equivalence(code, "f", code, "g").equivalent is True
        _agree(code, "f", "g", [(a,) for a in SAMPLES])

    def test_none_passed_for_an_any_parameter(self):
        code = '''
from typing import Any

def is_missing(a: Any):
    return a is None

def f():
    return 1 if is_missing(None) else 0

def g():
    return 1
'''
        assert verify_function_equivalence(code, "f", code, "g").equivalent is True


class TestRejected:

    def test_any_returned_is_rejected(self):
        r = simplify_function("from typing import Any\n\ndef f(a: Any):\n    return a\n", "f")
        assert r.status == "unsupported"
        assert "Any value" in r.reason

    def test_attribute_of_any_is_rejected(self):
        r = simplify_function("from typing import Any\n\ndef f(a: Any):\n    return a.size + 0\n", "f")
        assert r.status == "unsupported"

    def test_equality_between_two_any_values_is_rejected(self):
        # Python's == on arbitrary objects is not known, and is not symmetric in general.
        r = simplify_function(
            "from typing import Any\n\ndef f(a: Any, b: Any):\n    return 1 if a == b else 0\n", "f")
        assert r.status == "unsupported"

    def test_any_passed_for_an_int_parameter_is_rejected(self):
        code = '''
from typing import Any

def h(n: int):
    return n + 0

def f(a: Any):
    return h(a)
'''
        r = simplify_function(code, "f")
        assert r.status == "unsupported"


class TestContainersOfAny:

    def test_len_of_list_of_any_is_modelled(self):
        code = '''
from typing import Any, List

def f(xs: List[Any]):
    return len(xs) + 0

def g(xs: List[Any]):
    return len(xs)
'''
        assert verify_function_equivalence(code, "f", code, "g").equivalent is True
        _agree(code, "f", "g", [([None] * n,) for n in range(4)])

    def test_membership_in_dict_of_any_values_is_modelled(self):
        code = '''
from typing import Any, Dict

def f(d: Dict[str, Any], k: str):
    return k in d

def g(d: Dict[str, Any], k: str):
    return not (k not in d)
'''
        assert verify_function_equivalence(code, "f", code, "g").equivalent is True
        _agree(code, "f", "g", [({"a": 1}, "a"), ({"a": None}, "b"), ({}, "a")])

    def test_element_read_of_list_of_any_is_rejected(self):
        r = simplify_function(
            "from typing import Any, List\n\ndef f(xs: List[Any]):\n    y = xs[0]\n    return 1 if y is None else 0\n", "f")
        assert r.status == "unsupported"
        assert "container of Any values" in r.reason

    def test_iterating_list_of_any_counts_its_elements(self):
        code = '''
from typing import Any, List

def f(xs: List[Any]):
    n = 0
    for x in xs:
        n = n + 1
    return n

def g(xs: List[Any]):
    return len(xs)
'''
        assert verify_function_equivalence(code, "f", code, "g").equivalent is True
        _agree(code, "f", "g", [([None] * n,) for n in range(4)] + [([1, "a", {}],)])

    def test_element_of_list_of_any_used_as_a_number_is_rejected(self):
        code = '''
from typing import Any, List

def f(xs: List[Any]):
    total = 0
    for x in xs:
        total = total + x
    return total
'''
        r = simplify_function(code, "f")
        assert r.status == "unsupported"
        assert "Any value" in r.reason

    def test_list_of_any_passed_for_list_of_int_is_rejected(self):
        code = '''
from typing import Any, List

def h(xs: List[int]):
    return len(xs) + 0

def f(xs: List[Any]):
    return h(xs)
'''
        r = simplify_function(code, "f")
        assert r.status == "unsupported"
