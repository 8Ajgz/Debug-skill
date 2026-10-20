"""loop_verifier's expression translator: Python arithmetic semantics."""

import ast

import pytest
import z3

from ..loop_verifier import _expr_to_z3


def _translate(src):
    env = {"x": z3.Int("x"), "y": z3.Int("y")}
    return _expr_to_z3(ast.parse(src, mode="eval").body, env)


def test_true_division_is_real():
    """Python's x / 2 is real division; Z3's Int division would truncate."""
    expr = _translate("x / 2")
    assert expr.sort() == z3.RealSort()


def test_true_division_equals_half_not_truncated():
    expr = _translate("x / 2 == 1")
    s = z3.Solver()
    s.add(z3.Int("x") == 3, z3.Not(expr))
    assert s.check() == z3.sat, "3 / 2 is 1.5 in Python, so x / 2 == 1 must be false for x = 3"


@pytest.mark.parametrize("src", ["x // -2", "x % -2", "x % y", "x // y"])
def test_negative_or_symbolic_divisor_rejected(src):
    with pytest.raises(NotImplementedError):
        _translate(src)


def test_positive_literal_divisor_accepted():
    assert _translate("x % 3").sort() == z3.IntSort()
    assert _translate("x // 3").sort() == z3.IntSort()
