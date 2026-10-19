"""Decorator contract syntax: @requires, @ensures and @loop_invariant, as in the v11/v13 code.

Each form must give the same verdict as the comment form it replaces.
"""
import pytest

from ..contract_verifier import Z3_AVAILABLE, ContractVerifier, _decorator_clauses
from ..loop_verifier import extract_loop_invariants
from ..property_tester import property_test

pytestmark = pytest.mark.verification


def test_single_line_decorators_parse():
    code = '@requires("x > 0")\n@ensures("result >= 0")\ndef f(x):\n    return x\n'
    assert _decorator_clauses(code) == [("requires", "x > 0"), ("ensures", "result >= 0")]


def test_adjacent_literals_across_lines_are_joined():
    code = '@requires("x > 0 and "\n          "x < 9")\ndef f(x):\n    return x\n'
    assert _decorator_clauses(code) == [("requires", "x > 0 and x < 9")]


def test_single_quotes_are_accepted():
    code = "@ensures('result >= 0')\ndef f(x):\n    return x\n"
    assert _decorator_clauses(code) == [("ensures", "result >= 0")]


def test_text_inside_strings_is_not_a_decorator():
    code = 'msg = "@requires(\\"x > 0\\")"\n'
    assert _decorator_clauses(code) == []


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver not installed")
class TestSameVerdictAsComments:
    def test_decorator_form_verifies_like_comment_form(self):
        comments = "# Pre: x > 10\n# Post: x > 0\ndef f(x):\n    return x\n"
        decorators = '@requires("x > 10")\n@ensures("x > 0")\ndef f(x):\n    return x\n'
        assert (ContractVerifier.verify_contract(comments)["verified"]
                == ContractVerifier.verify_contract(decorators)["verified"] is True)

    def test_decorator_form_catches_violation(self):
        code = '@requires("x > 0")\n@ensures("x < 0")\ndef f(x):\n    return x\n'
        assert ContractVerifier.verify_contract(code)["verified"] is False

    def test_decorator_contract_feeds_the_simplifier(self):
        from ..contract_simplifier import ContractSimplifier
        result = ContractSimplifier().simplify(["x > 0"], ["x > -1"])
        assert [r.clause for r in result.removed] == ["x > -1"]


def test_loop_invariant_decorator_is_extracted_with_line_number():
    source = 'x = 0\n@loop_invariant("x >= 0")\nwhile x < 3:\n    x += 1\n# Invariant: x <= 3\n'
    found = [(i.expression, i.line_number) for i in extract_loop_invariants(source)]
    assert found == [("x >= 0", 2), ("x <= 3", 5)]


def test_property_test_ignores_contract_decorators_at_run_time():
    code = '@requires("x > 0")\n@ensures("result > 0")\ndef f(x):\n    return x\n'
    outcome = property_test(code)
    assert outcome["status"] == "passed"
