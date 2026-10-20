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


def test_return_inside_loop_is_judged_under_the_invariant():
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
    assert _verify(code)["verified"] is True


def test_return_inside_loop_without_invariant_is_unproven():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result >= 0
    i = 0
    while i < n:
        return i
        i = i + 1
    return 0
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_return_inside_loop_with_false_claim_fails_post():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result >= 1
    i = 0
    # Invariant: i >= 0
    while i < n:
        return i
        i = i + 1
    return 1
"""
    result = _verify(code)
    assert result["verified"] is False


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


def test_call_in_loop_body_havocs_what_it_can_change():
    code = """
def f(arr):
    # Pre: len(arr) > 0
    # Post: result == 5
    i = 0
    # Invariant: i >= 0 and i <= len(arr) and (i == 0 or arr[0] == 5)
    while i < len(arr):
        helper(arr)
        arr[i] = 5
        i = i + 1
    return arr[0]
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


def test_for_index_is_visible_in_the_invariant():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result == n
    total = 0
    # Invariant: total == i and i <= n
    for i in range(n):
        total = total + 1
    return total
"""
    assert _verify(code)["verified"] is True


def test_for_index_invariant_must_be_inductive():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result == n
    total = 0
    # Invariant: total == 0 and i <= n
    for i in range(n):
        total = total + 1
    return total
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_attribute_loop_with_invariant():
    code = """
def f(obj, n):
    # Pre: n >= 0 and obj.count == 0
    # Post: result == n
    i = 0
    # Invariant: obj.count == i and i <= n
    while i < n:
        obj.count = obj.count + 1
        i = i + 1
    return obj.count
"""
    assert _verify(code)["verified"] is True


def test_writes_to_two_objects_are_unproven():
    code = """
def f(a, b):
    # Pre: a.n >= 0 and b.n >= 0
    # Post: result >= 0
    a.n = -1
    return b.n
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_call_that_mutates_a_global_is_not_trusted():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    bump()
    return counter
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_fall_through_that_cannot_happen_is_fine():
    code = """
def f(x):
    # Post: result >= 0
    if x >= 0:
        return x
    if x < 0:
        return -x
"""
    assert _verify(code)["verified"] is True


def test_reachable_fall_through_is_unproven():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    if x > 0:
        return x
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_two_arrays_with_disjoint_writes_verify_in_every_grouping():
    # Writing index 0 of a and index 1 of b leaves a[0] alone, even when a is b.
    code = """
def f(a, b):
    # Pre: len(a) > 1 and len(b) > 1
    # Post: result == 5
    a[0] = 5
    b[1] = 6
    return a[0]
"""
    assert _verify(code)["verified"] is True


def test_aliased_writes_to_the_same_index_are_caught():
    # If a is b, the second write overwrites the first, so the result is 6.
    code = """
def f(a, b):
    # Pre: len(a) > 0 and len(b) > 0
    # Post: result == 5
    a[0] = 5
    b[0] = 6
    return a[0]
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_lengths_that_exclude_aliasing_let_the_proof_go_through():
    # With len(a) == 2 and len(b) == 3, a and b cannot be the same list.
    code = """
def f(a, b):
    # Pre: len(a) == 2 and len(b) == 3
    # Post: result == 5
    a[0] = 5
    b[0] = 6
    return a[0]
"""
    assert _verify(code)["verified"] is True


def test_two_objects_written_through_different_names_are_grouped():
    code = """
def f(p, q):
    # Pre: p.n >= 0 and q.n >= 0
    # Post: result >= 0
    p.n = 1
    q.n = 2
    return p.n
"""
    # If p is q, p.n is 2 here, which still satisfies the post, so this verifies.
    assert _verify(code)["verified"] is True


def test_five_arrays_with_writes_are_too_many_to_check():
    code = """
def f(a, b, c, d, e):
    # Pre: len(a) > 0
    # Post: result >= 0
    a[0] = 1
    b[0] = 1
    c[0] = 1
    d[0] = 1
    e[0] = 1
    return 0
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True
