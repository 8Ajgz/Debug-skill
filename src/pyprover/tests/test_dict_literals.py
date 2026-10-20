"""Dict literals bound by assignment, with int or str keys and scalar values of one sort.

Each claimed equivalence is checked against Python on the same inputs.
"""

from src.pyprover.equivalence_verifier import simplify_function, verify_function_equivalence


def _agree(code, f, g, args_list):
    ns = {}
    exec(code, ns)
    for args in args_list:
        assert ns[f](*args) == ns[g](*args), f"{f}{args} differs from {g}{args} in Python"


def test_value_read_from_dict_literal():
    code = '''
def f(x: int):
    d = {"a": x, "b": x + 1}
    return d["b"]

def g(x: int):
    return x + 1
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    _agree(code, "f", "g", [(x,) for x in range(-3, 4)])


def test_membership_in_annotated_dict_literal():
    code = '''
from typing import Dict

def f(x: int):
    d: Dict[str, int] = {"a": x}
    return 1 if "a" in d else 0

def g(x: int):
    return 1
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    _agree(code, "f", "g", [(x,) for x in range(-2, 3)])


def test_repeated_key_keeps_its_last_value():
    code = '''
def f(x: int):
    d = {"a": 1, "a": x}
    return d["a"]

def g(x: int):
    return x
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    _agree(code, "f", "g", [(x,) for x in range(-2, 3)])


def test_integer_keys():
    code = '''
def f(x: int):
    d = {1: x, 2: 5}
    return d[2] + 0 * d[1]

def g(x: int):
    return 5
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    _agree(code, "f", "g", [(x,) for x in range(-2, 3)])


def test_missing_key_is_not_proven():
    r = simplify_function('def f(x: int):\n    d = {"a": x}\n    return d["b"]\n', "f")
    assert r.status == "unsupported"


def test_mixed_value_sorts_are_rejected():
    r = simplify_function('def f(x: int):\n    d = {"a": x, "b": "s"}\n    return 0\n', "f")
    assert r.status == "unsupported"
    assert "one sort" in r.reason


def test_dict_unpacking_is_rejected():
    r = simplify_function('def f(x: int):\n    d = {**{}, "a": x}\n    return 0\n', "f")
    assert r.status == "unsupported"
