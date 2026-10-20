"""
Regression tests for postconditions that mention ``result``.

Before this fix, a postcondition on ``result`` only had to be satisfiable, so a
false postcondition such as ``result < 0`` for ``return x * 2`` reported
verified=True. The return expression is now substituted for ``result`` and the
preconditions must imply it. Anything that cannot be checked is INCONCLUSIVE,
which is never reported as a pass.
"""

import pytest
from ..contract_verifier import ContractVerifier

pytest.importorskip("z3")


def _verify(code):
    return ContractVerifier.verify_contract(code)


def test_false_result_postcondition_fails():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result < 0
    return x * 2
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result["postconditions_ok"] is False
    assert any("NOT implied" in d for d in result["details"])


def test_true_result_postcondition_verifies():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    return x * 2
"""
    result = _verify(code)
    assert result["verified"] is True
    assert not result.get("inconclusive")


def test_len_of_result_is_substituted():
    code = """
def f(arr):
    # Pre: len(arr) > 0
    # Post: len(result) == len(arr)
    return arr
"""
    assert _verify(code)["verified"] is True


def test_branching_body_is_inconclusive_not_verified():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    if x > 5:
        return x
    return x * 2
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True
    assert result["postconditions_ok"] is True


def test_no_annotations_is_inconclusive_not_verified():
    result = _verify("def f(x):\n    return x * 2\n")
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_inconclusive_result_is_not_reported_as_failure():
    result = _verify("def f(x):\n    # Post: result >= 0\n    if x:\n        return x\n    return 0\n")
    assert result.get("inconclusive") is True
    assert not any(d.startswith("FAIL") for d in result["details"])


def test_straight_line_assignments_are_inlined():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 1
    y = x * 2
    return y + 1
"""
    assert _verify(code)["verified"] is True


def test_false_claim_through_assignment_fails():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result < 0
    y = x * 2
    z = y + 1
    return z
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result["postconditions_ok"] is False


def test_reassignment_uses_the_latest_value():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    x = x + 1
    x = x * 2
    return x
"""
    assert _verify(code)["verified"] is True


def test_parameter_rebound_to_a_constant():
    code = """
def f(y):
    # Pre: y >= 0
    # Post: result >= 0
    y = 5
    return y
"""
    assert _verify(code)["verified"] is True


def test_annotated_assignment_is_inlined():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    y: int = x * 3
    return y
"""
    assert _verify(code)["verified"] is True


def test_constant_postcondition_on_result_verifies():
    code = """
def f(y):
    # Pre: y >= 0
    # Post: result >= 0
    return 5
"""
    assert _verify(code)["verified"] is True
