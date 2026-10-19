"""Tests for conditional postconditions: ``# Post: if <cond>: <clause>``, checked as Implies(cond, clause)."""
import pytest

from ..contract_verifier import Z3_AVAILABLE, ContractVerifier, _clause_to_z3, _conditional_parts
from ..property_tester import evaluate_clause, property_test

pytestmark = pytest.mark.verification


def _verify(pre, post):
    code = f"# Pre: {pre}\n# Post: {post}\ndef f(x):\n    return x\n"
    return ContractVerifier.verify_contract(code)


class TestConditionalParts:
    def test_splits_if_form(self):
        assert _conditional_parts("if x > 5: x > 0") is not None

    @pytest.mark.parametrize("clause", [
        "x > 0",
        "if x > 5: x > 0 else x < 0",
        "if x > 5: y = 1",
        "x > 0 and x < 9",
        "if x > 5",
        "arr[1:2] == arr[1:2]",
    ])
    def test_other_forms_are_not_conditional(self, clause):
        assert _conditional_parts(clause) is None


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver not installed")
class TestVerifyConditionalPostconditions:
    def test_translates_to_implies(self):
        import z3
        expr = _clause_to_z3("if x > 5: x > 0", {"x": z3.Int("x")})
        assert expr is not None
        assert expr.decl().name() == "=>"

    def test_implied_conditional_verifies(self):
        result = _verify("x > 10", "if x > 5: x > 0")
        assert result["verified"] is True
        assert any("implied by preconditions" in d for d in result["details"])

    def test_violated_conditional_fails_with_counterexample(self):
        result = _verify("x > 0", "if x > 5: x > 100")
        assert result["verified"] is False
        assert any("NOT implied" in d for d in result["details"])

    def test_condition_never_true_under_precondition_is_vacuous(self):
        result = _verify("x > 0", "if x < -10: x > 100")
        assert result["verified"] is True

    def test_else_form_is_skipped_not_guessed(self):
        result = _verify("x > 0", "if x > 5: x > 0 else x < 0")
        assert any("skipped" in d for d in result["details"])


class TestPropertyTesterConditionals:
    def test_evaluate_true_when_condition_false(self):
        assert evaluate_clause("if x > 5: x > 100", {"x": 3}) is True

    def test_evaluate_consequent_when_condition_true(self):
        assert evaluate_clause("if x > 5: x > 100", {"x": 7}) is False

    def test_conditional_contract_passes(self):
        code = "# Pre: x > 0\n# Post: if x > 5: result > 5\ndef f(x):\n    return x\n"
        assert property_test(code)["status"] == "passed"

    def test_conditional_contract_fails_with_counterexample(self):
        code = "# Pre: x > 0\n# Post: if x > 5: result > 100\ndef g(x):\n    return x\n"
        outcome = property_test(code)
        assert outcome["status"] == "failed"
        assert outcome["counterexample"]["x"] > 5


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver not installed")
class TestSimplifierConditionals:
    def test_implied_conditional_is_removed(self):
        from ..contract_simplifier import ContractSimplifier
        result = ContractSimplifier().simplify(["x > 0"], ["if x > 5: x > 0"])
        assert [r.clause for r in result.removed] == ["if x > 5: x > 0"]

    def test_conditional_clause_is_not_dropped_when_not_implied(self):
        from ..contract_simplifier import ContractSimplifier
        result = ContractSimplifier().simplify(["x > 0"], ["if x > 5: x > 100"])
        assert result.removed == []
