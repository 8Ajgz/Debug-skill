"""simplify_function: soundness of the simplification and of its Python output.

Every simplified Python expression is evaluated against the original function
on a grid of inputs. Python's // and % are only handled for positive literal
divisors, because Z3 uses Euclidean division.
"""

import ast
import inspect
import itertools
import math

import pytest

from ..equivalence_verifier import (
    simplify_function,
    verify_function_equivalence,
    _z3_to_python,
    _find_function,
    _function_to_symbolic,
    UnsupportedConstructError,
)

try:
    import z3
except ImportError:  # pragma: no cover
    z3 = None

pytestmark = pytest.mark.skipif(z3 is None, reason="z3-solver not installed")

GRID = range(-6, 7)


def _param_domains(code, name):
    """Input values per parameter: True/False for `bool`-annotated, else GRID."""
    node = _find_function(code, name)
    return [
        (arg.arg, [True, False] if isinstance(arg.annotation, ast.Name)
         and arg.annotation.id == "bool" else GRID)
        for arg in node.args.args
    ]


def _assert_translation_matches_original(code, name):
    """Render the translated Z3 expression of the ORIGINAL code as Python and
    compare with the original on every input. This checks the translation
    itself, whatever simplify_function decides to report."""
    node = _find_function(code, name)
    expr = _function_to_symbolic(node, {}, 64)
    rendered = _z3_to_python(expr, frozenset(a.arg for a in node.args.args))
    ns = {}
    exec(code, ns)
    domains = _param_domains(code, name)
    names = [n for n, _ in domains]
    for vals in itertools.product(*[d for _, d in domains]):
        expected = ns[name](*vals)
        got = eval(rendered, {}, dict(zip(names, vals)))
        assert got == expected, f"{name}{vals}: original={expected!r}, translated={got!r} ({rendered})"


def _assert_python_matches_original(code, name):
    r = simplify_function(code, name)
    assert r.status in ("simplified", "already_simplest"), r.summary()
    if r.status == "already_simplest":
        return r  # nothing rewritten, so there is no new Python to check
    assert r.simplified_python is not None, "no Python rendering produced"
    ns = {}
    exec(code, ns)
    func = ns[name]
    domains = [d for _, d in _param_domains(code, name)]
    params = list(inspect.signature(func).parameters)
    for vals in itertools.product(*domains):
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


class TestExpandedSubset:

    @pytest.mark.parametrize("code", [
        "def f(x: int) -> int:\n    y: int = x + 0\n    return y\n",
        "def f(x, y):\n    a, b = y, x\n    return a - b\n",
        "def f(x, y):\n    a, b = (y if x > 0 else 0), x\n    return a - b\n",
        "def f(x):\n    a = b = x * 1\n    return a + b\n",
        "def f(x):\n    return x ** 2\n",
        "def f(x):\n    return x ** 3 - x ** 0\n",
        "def f(flag: bool, x):\n    if flag:\n        return x\n    return x + 0\n",
        "def f(flag: bool):\n    return not flag\n",
        "def f(a: bool, b: bool):\n    return a and not b\n",
    ])
    def test_translation_matches_original(self, code):
        _assert_translation_matches_original(code, "f")

    def test_swap_uses_pre_assignment_values(self):
        """a, b = b, a must read both old values before binding either name."""
        code = "def f(x, y):\n    x, y = y, x\n    return x * 10 + y\n"
        _assert_translation_matches_original(code, "f")

    def test_tuple_length_mismatch_is_unsupported(self):
        r = simplify_function("def f(x, y):\n    a, b = x\n    return a\n", "f")
        assert r.status == "unsupported"

    def test_attribute_target_still_unsupported(self):
        r = simplify_function("def f(x):\n    x.a = 1\n    return x\n", "f")
        assert r.status == "unsupported"

    @pytest.mark.parametrize("expr", ["x ** -1", "2 ** x", "x ** 2.0", "x ** 17"])
    def test_non_literal_or_large_power_unsupported(self, expr):
        r = simplify_function(f"def f(x):\n    return {expr}\n", "f")
        assert r.status == "unsupported"
        assert "'**'" in r.reason

    def test_unannotated_bool_use_still_unsupported(self):
        """Without an annotation the parameter is an Int, so `not flag` cannot
        be translated. This is the documented boundary, not a regression."""
        r = simplify_function("def f(flag):\n    return not flag\n", "f")
        assert r.status == "unsupported"

    def test_bool_annotated_equivalence(self):
        a = "def f(flag: bool):\n    if flag:\n        return 1\n    return 2\n"
        b = "def g(flag: bool):\n    return 1 if flag else 2\n"
        assert verify_function_equivalence(a, "f", b, "g").equivalent is True

    def test_bool_versus_int_parameter_is_unsupported(self):
        a = "def f(flag: bool):\n    return 1\n"
        b = "def g(flag: int):\n    return 1\n"
        r = verify_function_equivalence(a, "f", b, "g")
        assert r.status == "unsupported"
        assert "parameter types differ" in r.reason

    def test_power_equivalence_proven(self):
        a = "def f(x):\n    return x ** 2\n"
        b = "def g(x):\n    return x * x\n"
        assert verify_function_equivalence(a, "f", b, "g").equivalent is True
