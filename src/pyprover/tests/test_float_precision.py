"""Float precision: float contracts are checked over the reals, not the integers.

Before this, every variable was a Z3 Int and float literals were passed through as
Python floats, so float contracts were silently checked over integers. These tests
pin the cases that were wrong.
"""
import pytest

from ..contract_verifier import Z3_AVAILABLE, ContractVerifier, _clause_to_z3, float_annotated_params

pytestmark = [pytest.mark.verification, pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver not installed")]


def _verify(pre, post, header="def f(x):"):
    code = f"# Pre: {pre}\n# Post: {post}\n{header}\n    return x\n"
    return ContractVerifier.verify_contract(code)


class TestSoundness:
    def test_float_violation_is_not_hidden(self):
        # x = 0.6 meets the precondition and violates the postcondition.
        assert _verify("x > 0.5", "x >= 1")["verified"] is False

    def test_float_interval_is_not_empty(self):
        # The reals in (0.5, 1) exist, so the precondition is satisfiable.
        result = _verify("x > 0.5 and x < 1", "x > 0")
        assert result["verified"] is True
        assert result["preconditions_ok"] is True

    def test_true_division_of_integers(self):
        # Python: 1 / 2 == 0.5 > 0, so x / 2 > 0 holds for every x > 0.
        assert _verify("x > 0", "x / 2 > 0")["verified"] is True


class TestAnnotations:
    def test_float_annotation_makes_variable_real(self):
        # Over the integers x == 1 is forced; over the reals x = 0.5 violates it.
        assert _verify("x > 0 and x < 2", "x == 1")["verified"] is True
        assert _verify("x > 0 and x < 2", "x == 1", header="def f(x: float):")["verified"] is False

    def test_annotation_scan(self):
        code = "def f(x: float, n: int):\n    return x\ndef g(y: float):\n    return y\n"
        assert sorted(float_annotated_params(code)) == ["x", "y"]

    def test_unparseable_code_has_no_annotations(self):
        assert float_annotated_params("def f(:") == []


class TestExactLiterals:
    def test_decimal_literal_is_exact(self):
        # 0.1 is exactly 1/10 in the model, so x > 0.1 implies x > 0.0999.
        assert _verify("x > 0.1", "x > 0.0999")["verified"] is True

    def test_boundary_is_not_included(self):
        # x = 0.1 satisfies x >= 0.1 but not x > 0.1.
        assert _verify("x >= 0.1", "x > 0.1")["verified"] is False


class TestFloorOperatorsSkipped:
    def test_floor_division_over_reals_is_skipped(self):
        result = _verify("x > 0.5", "x // 2 >= 0")
        assert any("skipped" in d for d in result["details"])

    def test_modulo_over_reals_is_skipped(self):
        assert _clause_to_z3("x % 2 == 0", {"x": _real("x")}) is None

    def test_integer_floor_division_still_translates(self):
        import z3
        assert _clause_to_z3("x // 2 >= 0", {"x": z3.Int("x")}) is not None


def _real(name):
    import z3
    return z3.Real(name)


class TestSimplifierSemantics:
    def test_redundant_float_bound_removed(self):
        from ..contract_simplifier import ContractSimplifier
        result = ContractSimplifier().simplify(["x > 0.5"], ["x > 0.4"])
        assert [r.clause for r in result.removed] == ["x > 0.4"]
