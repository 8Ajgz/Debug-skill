"""Tests for Hypothesis-based contract property testing."""
import pytest

from .. import property_tester as pt
from ..property_tester import UnsupportedClause, evaluate_clause, property_test

pytestmark = pytest.mark.verification


def _needs_hypothesis(fn):
    return pytest.mark.skipif(not pt.HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")(fn)


class TestEvaluateClause:
    def test_arithmetic_and_comparison(self):
        assert evaluate_clause("x * 2 + 1 > x", {"x": 3}) is True

    def test_result_aliases_resolve(self):
        assert evaluate_clause("retval >= 0", {"x": 1, "result": 4}) is True

    def test_allowed_calls(self):
        assert evaluate_clause("max(x, 0) == abs(x) or x < 0", {"x": -2}) is True

    def test_chained_comparison(self):
        assert evaluate_clause("0 <= x < 10", {"x": 5}) is True

    def test_disallowed_syntax_is_rejected(self):
        with pytest.raises(UnsupportedClause):
            evaluate_clause("x ** 2 >= 0", {"x": 1})

    def test_unknown_name_is_rejected(self):
        with pytest.raises(UnsupportedClause):
            evaluate_clause("y > 0", {"x": 1})

    def test_no_eval_of_attribute_access(self):
        with pytest.raises(UnsupportedClause):
            evaluate_clause("x.__class__", {"x": 1})


@_needs_hypothesis
class TestPropertyTest:
    def test_correct_contract_passes(self):
        code = "# Pre: x >= 0\n# Post: result >= 0\ndef f(x):\n    return x * x\n"
        outcome = property_test(code)
        assert outcome["status"] == "passed"
        assert outcome["examples"] > 0

    def test_violated_postcondition_fails_with_real_counterexample(self):
        code = "# Pre: x > 0\n# Post: result > x\ndef g(x):\n    return x\n"
        outcome = property_test(code)
        assert outcome["status"] == "failed"
        inputs = outcome["counterexample"]
        assert inputs["x"] > 0
        assert not (inputs["x"] > inputs["x"])  # the violated clause, re-checked on the reported inputs

    def test_exception_in_function_is_a_failure(self):
        code = "# Post: result >= 0\ndef r(x):\n    return 1 // x\n"
        outcome = property_test(code)
        assert outcome["status"] == "failed"
        # x = -1 violates the postcondition before x = 0 raises; either is a real failure
        assert "ZeroDivisionError" in outcome["reason"] or "postcondition" in outcome["reason"]

    def test_postcondition_error_discards_input_not_fails(self):
        code = "# Post: 10 // x > -1000\ndef p(x):\n    return x\n"
        outcome = property_test(code)
        assert outcome["status"] == "passed"

    def test_unsupported_clause_skips(self):
        code = "# Post: x ** 2 >= 0\ndef s(x):\n    return x\n"
        outcome = property_test(code)
        assert outcome["status"] == "skipped"
        assert "unsupported" in outcome["reason"]

    def test_no_postconditions_skips(self):
        outcome = property_test("# Pre: x > 0\ndef f(x):\n    return x\n")
        assert outcome["status"] == "skipped"

    def test_non_plain_parameters_skip(self):
        code = "# Post: result >= 0\ndef f(*args):\n    return 0\n"
        outcome = property_test(code)
        assert outcome["status"] == "skipped"

    def test_no_function_skips(self):
        outcome = property_test("# Post: x > 0\nx = 1\n")
        assert outcome["status"] == "skipped"


def test_missing_hypothesis_skips(monkeypatch):
    monkeypatch.setattr(pt, "HYPOTHESIS_AVAILABLE", False)
    outcome = property_test("# Post: result >= 0\ndef f(x):\n    return x\n")
    assert outcome == {"status": "skipped", "reason": "hypothesis is not installed"}
