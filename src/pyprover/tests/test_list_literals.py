"""List literals bound by an annotated assignment, as `xs: List[int] = [...]` binds them.

An assignment `xs = [...]` already binds a list literal. The annotated form binds the same value,
so the same checks apply: element reads are guarded, and the length is the number of elements.
"""

from src.pyprover.equivalence_verifier import simplify_function, verify_function_equivalence


def test_annotated_list_literal_length_is_modelled():
    code = '''
from typing import List

def f(x: int):
    xs: List[int] = [x, x + 1, 2]
    return len(xs)

def g(x: int):
    return 3
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True


def test_annotated_list_literal_element_read_is_modelled():
    code = '''
from typing import List

def f(x: int):
    xs: List[int] = [x, x + 1]
    return xs[1]

def g(x: int):
    return x + 1
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True


def test_annotated_empty_list_is_modelled():
    code = '''
from typing import List

def f(x: int):
    xs: List[int] = []
    return x + len(xs)

def g(x: int):
    return x
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True


def test_annotated_list_element_out_of_range_is_not_proven():
    code = '''
from typing import List

def f(x: int):
    xs: List[int] = [x]
    return xs[1]
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
