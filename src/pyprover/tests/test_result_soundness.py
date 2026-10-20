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


def test_while_loop_body_is_inconclusive_not_verified():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    while x > 5:
        x = x - 1
    return x
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
    result = _verify("def f(x):\n    # Post: result >= 0\n    while x:\n        x = x - 1\n    return x\n")
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


def test_if_else_both_paths_checked():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    if x > 5:
        return x
    else:
        return x * 2
"""
    assert _verify(code)["verified"] is True


def test_false_claim_on_one_branch_fails():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 1
    if x > 5:
        return x
    return 0
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result["postconditions_ok"] is False


def test_assignment_inside_branch_is_merged_after_it():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    y = 0
    if x > 5:
        y = x
    else:
        y = x * 2
    return y
"""
    assert _verify(code)["verified"] is True


def test_constant_range_loop_is_unrolled():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result == 3
    total = 0
    for i in range(3):
        total = total + i
    return total
"""
    assert _verify(code)["verified"] is True


def test_wrong_loop_result_fails():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result == 4
    total = 0
    for i in range(3):
        total = total + i
    return total
"""
    assert _verify(code)["verified"] is False


def test_return_inside_loop_stops_iteration():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result == 1
    for i in range(5):
        if i == 1:
            return i
    return 0
"""
    assert _verify(code)["verified"] is True


def test_symbolic_range_bound_is_inconclusive():
    code = """
def f(n):
    # Pre: n >= 0
    # Post: result >= 0
    total = 0
    for i in range(n):
        total = total + i
    return total
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_subscript_write_is_inconclusive():
    code = """
def f(arr):
    # Pre: len(arr) > 0
    # Post: result >= 0
    arr[0] = 5
    return 5
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_attribute_write_is_inconclusive():
    code = """
def f(obj):
    # Pre: obj.n >= 0
    # Post: result >= 0
    obj.n = -1
    return 5
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_impure_call_statement_is_inconclusive():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    print(x)
    return x
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True


def test_pure_builtin_call_statement_is_skipped():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    len(str(x))
    return x
"""
    assert _verify(code)["verified"] is True


def test_path_without_return_is_inconclusive():
    code = """
def f(x):
    # Pre: x >= 0
    # Post: result >= 0
    if x > 5:
        return x
"""
    result = _verify(code)
    assert result["verified"] is False
    assert result.get("inconclusive") is True
