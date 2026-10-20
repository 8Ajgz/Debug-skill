"""Loops over a tuple or list literal, and over enumerate of a list.

A literal has a fixed number of elements, and enumerate of a modelled list has the list's
length, so both unroll exactly. Each claimed equivalence is checked against Python.
"""

import itertools

from src.pyprover.equivalence_verifier import simplify_function, verify_function_equivalence


def _agree(code, f, g, args_list):
    ns = {}
    exec(code, ns)
    for args in args_list:
        assert ns[f](*args) == ns[g](*args), f"{f}{args} differs from {g}{args} in Python"


def test_loop_over_tuple_literal_sums_its_elements():
    code = '''
def f(x: int):
    total = 0
    for v in (x, x + 1, 2):
        total = total + v
    return total

def g(x: int):
    return 2 * x + 3
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    _agree(code, "f", "g", [(x,) for x in range(-3, 4)])


def test_loop_over_list_literal_keeps_last_value_after_loop():
    code = '''
def f(x: int):
    for v in [x, 5]:
        pass
    return v

def g(x: int):
    return 5
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    _agree(code, "f", "g", [(x,) for x in range(-3, 4)])


def test_loop_over_empty_literal_does_not_run_the_body():
    code = '''
def f(x: int):
    total = x
    for v in []:
        total = total + 1
    return total

def g(x: int):
    return x
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True


def test_return_inside_literal_loop_is_rejected():
    code = '''
def f(x: int):
    for v in (x, 1):
        return v
    return 0
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"


def test_enumerate_over_list_parameter():
    code = '''
from typing import List

def f(xs: List[int]):
    total = 0
    for i, v in enumerate(xs):
        total = total + i * v
    return total

def g(xs: List[int]):
    total = 0
    for i in range(len(xs)):
        total = total + i * xs[i]
    return total
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    lists = [[], [4], [1, -2], [3, 0, 7]]
    _agree(code, "f", "g", [(xs,) for xs in lists])


def test_enumerate_element_of_list_of_any_is_rejected():
    code = '''
from typing import Any, List

def f(xs: List[Any]):
    total = 0
    for i, v in enumerate(xs):
        total = total + i
    return total
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
