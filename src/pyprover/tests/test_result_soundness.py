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


def test_multi_statement_body_is_inconclusive_not_verified():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    y = x * 2
    return y
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
    result = _verify("def f(x):\n    # Post: result >= 0\n    y = x\n    return y\n")
    assert result.get("inconclusive") is True
    assert not any(d.startswith("FAIL") for d in result["details"])
