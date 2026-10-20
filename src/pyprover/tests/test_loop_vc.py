"""
Tests for the loop and array-write model in loop_vc.

A postcondition on ``result`` is proven only from a loop invariant that holds on
entry, is preserved by the body, and implies the postcondition at exit. A wrong
invariant leaves the postcondition unproven, never failed.
"""

import pytest
from ..contract_verifier import ContractVerifier

pytest.importorskip("z3")


def _verify(code):
    return ContractVerifier.verify_contract(code)


def test_while_loop_with_inductive_invariant_proves_post():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result == n
    i = 0
    # Invariant: i >= 0 and i <= n
    while i < n:
        i = i + 1
    return i
"""
    assert _verify(code)["verified"] is True


def test_while_loop_without_invariant_is_unproven():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result == n
    i = 0
    while i < n:
        i = i + 1
    return i
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_non_inductive_invariant_is_unproven_not_failed():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result == n
    i = 0
    # Invariant: i == 0
    while i < n:
        i = i + 1
    return i
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result["postconditions_ok"] is True
    assert result.get("inconclusive") is True


def test_wrong_post_with_correct_loop_fails_nothing_proven():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result == n + 1
    i = 0
    # Invariant: i >= 0 and i <= n
    while i < n:
        i = i + 1
    return i
"""
    result = _verify(code)
    assert result["verified"] is False
    assert not any(d.startswith("FAIL") for d in result["details"])


def test_loop_over_array_parameter_with_invariant():
    code = """
def f(arr):
    # Pre: len(arr) >= 0
    # Post: result >= 0
    count = 0
    # Invariant: count >= 0
    for x in arr:
        count = count + 1
    return count
"""
    assert _verify(code)["verified"] is True


def test_array_loop_invariant_tracks_written_elements():
    code = """
def fill_first(arr):
    # Pre: len(arr) >= 1
    # Post: result == 5
    i = 0
    # Invariant: i >= 0 and i <= len(arr) and (i == 0 or arr[0] == 5)
    while i < len(arr):
        arr[i] = 5
        i = i + 1
    return arr[0]
"""
    assert _verify(code)["verified"] is True


def test_wrong_element_value_breaks_preservation_not_post():
    code = """
def fill_first(arr):
    # Pre: len(arr) >= 1
    # Post: result == 5
    i = 0
    # Invariant: i >= 0 and i <= len(arr) and (i == 0 or arr[0] == 5)
    while i < len(arr):
        arr[i] = 6
        i = i + 1
    return arr[0]
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_negative_index_write_is_normalised():
    code = """
def f(arr):
    # Pre: len(arr) > 0
    # Post: result == 7
    arr[-1] = 7
    return arr[len(arr) - 1]
"""
    assert _verify(code)["verified"] is True


def test_symbolic_range_loop_with_invariant():
    # The index is not visible in the invariant, so the invariant is about total alone.
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result >= 0
    total = 0
    # Invariant: total >= 0
    for i in range(n):
        total = total + 1
    return total
"""
    assert _verify(code)["verified"] is True


def test_return_inside_loop_is_unproven():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result >= 0
    i = 0
    # Invariant: i >= 0
    while i < n:
        return i
        i = i + 1
    return 0
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_bare_array_use_is_not_verified():
    # The inliner treats a bare parameter as a number, so this reports a
    # counterexample rather than a proof. That is a known gap, not a pass.
    code = """
def f(arr):
    # Pre: len(arr) > 0
    # Post: result >= 0
    return arr
"""
    assert _verify(code)["verified"] is False


def test_loop_over_local_list_is_unproven():
    code = """
def f(n):
    # Post: result >= 0
    xs = [1, 2]
    total = 0
    # Invariant: total >= 0
    for x in xs:
        total = total + x
    return total
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_loop_body_with_an_unmodelled_call_is_unproven():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result >= 0
    i = 0
    # Invariant: i >= 0
    while i < n:
        print(i)
        i = i + 1
    return i
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_invariant_false_on_entry_is_unproven():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result >= 0
    i = 5
    # Invariant: i == 0
    while i < n:
        i = i + 1
    return i
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_true_but_too_weak_invariant_does_not_prove_post():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result == n
    i = 0
    # Invariant: i >= 0
    while i < n:
        i = i + 1
    return i
"""
    result = _verify(code)
    assert result["verified"] is False
    assert not any(d.startswith("FAIL") for d in result["details"])
