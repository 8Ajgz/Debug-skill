"""Quantified loop invariants, checked in INIT and PRESERVATION by the loop verifier.

The verifier still models one step (the iteration variable increases by 1) and
does not model the loop body or arrays. These tests cover only what it can check.
"""
import pytest

from ..contract_verifier import Z3_AVAILABLE
from ..loop_verifier import LoopInvariant, _parse_invariant_expr, verify_loop_invariant

pytestmark = [pytest.mark.verification, pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver not installed")]


def _check(expr):
    return verify_loop_invariant(LoopInvariant(expression=expr, loop_var="i"), param_names=["i"])


def test_quantifier_translates_to_forall():
    import z3
    expr = _parse_invariant_expr("all(k >= 0 for k in range(0, i))", {"i": z3.Int("i")})
    assert isinstance(expr, z3.BoolRef)
    assert z3.is_quantifier(expr) and expr.is_forall()


def test_any_translates_to_exists():
    import z3
    expr = _parse_invariant_expr("any(k == i for k in range(0, i + 1))", {"i": z3.Int("i")})
    assert z3.is_quantifier(expr) and not expr.is_forall()


def test_preserved_quantified_invariant():
    # Holds for every prefix [0, i) if i >= 0, and extends to [0, i + 1).
    result = _check("all(k >= 0 for k in range(0, i))")
    assert result.init_holds is True
    assert result.preservation_holds is True


def test_quantified_invariant_that_breaks_at_the_next_step():
    # At i = 3 the prefix [0, 3) satisfies k < 3, but k = 3 is in the next prefix.
    result = _check("all(k < 3 for k in range(0, i))")
    assert result.init_holds is True
    assert result.preservation_holds is False
    assert result.counterexample is not None


def test_unsupported_quantifier_domain_skips_instead_of_guessing():
    result = _check("all(k >= 0 for k in items)")
    assert result.skipped is True
