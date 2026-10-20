"""simplify_function: soundness of the simplification and of its Python output.

Every simplified Python expression is evaluated against the original function
on a grid of inputs. Python's // and % are only handled for positive literal
divisors, because Z3 uses Euclidean division.
"""

import inspect
import itertools
import math

import pytest

from ..equivalence_verifier import (
    simplify_function,
    verify_function_equivalence,
    _z3_to_python,
    UnsupportedConstructError,
)

try:
    import z3
except ImportError:  # pragma: no cover
    z3 = None

pytestmark = pytest.mark.skipif(z3 is None, reason="z3-solver not installed")

GRID = range(-6, 7)


def _assert_python_matches_original(code, name):
    r = simplify_function(code, name)
    assert r.status in ("simplified", "already_simplest"), r.summary()
    if r.status == "already_simplest":
        return r  # nothing rewritten, so there is no new Python to check
    assert r.simplified_python is not None, "no Python rendering produced"
    ns = {}
    exec(code, ns)
    func = ns[name]
    params = list(inspect.signature(func).parameters)
    for vals in itertools.product(GRID, repeat=len(params)):
        expected = func(*vals)
        got = eval(r.simplified_python, {}, dict(zip(params, vals)))
        assert got == expected or math.isclose(got, expected, rel_tol=1e-9), (
            f"{name}{vals}: original={expected!r}, simplified={got!r} "
            f"({r.simplified_python})"
        )
    return r


class TestPythonOutputMatchesOriginal:

    def test_redundant_arithmetic(self):
        _assert_python_matches_original("def f(x):\n    return x * 1 + 0\n", "f")

    def test_abs_like_branch(self):
        _assert_python_matches_original(
            "def f(x):\n    if x > 0:\n        return x\n    return -x\n", "f"
        )

    def test_nested_branches_two_params(self):
        code = (
            "def f(x, y):\n"
            "    if x > y:\n"
            "        return x\n"
            "    else:\n"
            "        return y\n"
        )
        _assert_python_matches_original(code, "f")

    def test_chained_comparison_as_boolean(self):
        _assert_python_matches_original(
            "def f(x):\n    return 0 < x and x < 10\n", "f"
        )

    def test_true_division_matches_float_result(self):
        _assert_python_matches_original("def f(x):\n    return x / 2\n", "f")

    def test_positive_floor_division_and_mod(self):
        _assert_python_matches_original(
            "def f(x):\n    return x // 3 + x % 3\n", "f"
        )

    def test_unrolled_loop(self):
        code = (
            "def f(x):\n"
            "    s = 0\n"
            "    for i in range(3):\n"
            "        s += x * i\n"
            "    return s\n"
        )
        _assert_python_matches_original(code, "f")


class TestDivisionSoundness:

    def test_negative_mod_divisor_is_unsupported(self):
        r = simplify_function("def f(x):\n    return x % -2\n", "f")
        assert r.status == "unsupported"
        assert "positive integer literal" in r.reason

    def test_negative_floor_divisor_is_unsupported(self):
        r = simplify_function("def f(x):\n    return x // -2\n", "f")
        assert r.status == "unsupported"

    def test_symbolic_divisor_is_unsupported(self):
        r = simplify_function("def f(x, y):\n    return x % y\n", "f")
        assert r.status == "unsupported"

    def test_negative_mod_not_proven_equal_to_positive_mod(self):
        """Python: 7 % -2 == -1 but 7 % 2 == 1. This used to be proven equal."""
        r = verify_function_equivalence(
            "def f(x):\n    return x % -2\n", "f",
            "def g(x):\n    return x % 2\n", "g",
        )
        assert r.equivalent is not True


class TestRenderer:

    def test_unknown_operator_raises(self):
        x = z3.Int("x")
        with pytest.raises(UnsupportedConstructError):
            _z3_to_python(x ** 2)

    def test_negative_constant_parenthesised(self):
        assert _z3_to_python(z3.IntVal(-3)) == "(-3)"

    def test_rational_constant(self):
        assert _z3_to_python(z3.RealVal("1/2")) == "(1/2)"

    def test_no_rewrite_means_no_python_output(self):
        r = simplify_function("def f(x):\n    return x\n", "f")
        assert r.status == "already_simplest"
        assert r.simplified_python is None


class TestOnlyRealReductionsReported:

    def test_already_minimal_product(self):
        r = simplify_function("def f(x, y):\n    return x * y\n", "f")
        assert r.status == "already_simplest"

    def test_reordering_alone_is_not_reported_as_unrelated_change(self):
        """Whatever Z3 does to term order, a reported simplification must still
        be equal to the original (checked by the rendering tests above)."""
        r = simplify_function("def f(x):\n    return 3 * x + 0\n", "f")
        assert r.status in ("simplified", "already_simplest")
        if r.status == "simplified":
            _assert_python_matches_original("def f(x):\n    return 3 * x + 0\n", "f")
