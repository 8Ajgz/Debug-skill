"""float parameters, and division by a value that may be zero.

Floats are modelled as exact reals, and every result that depends on one says so.
A division whose divisor may be zero is rejected, unless the code guards it, or a
handler catches ZeroDivisionError.
"""

import pytest

from ..equivalence_verifier import simplify_function, verify_function_equivalence

GRID = [-3, -1, 0, 1, 2]


def _py(src, name, *args):
    ns = {}
    exec(src, ns)
    try:
        return ns[name](*args)
    except ZeroDivisionError:
        return "raised"


class TestFloat:

    def test_float_parameter_is_modelled_with_note(self):
        r = verify_function_equivalence(
            "def f(x: float):\n    return x + 1 - 1\n", "f",
            "def g(x: float):\n    return x\n", "g")
        assert r.equivalent is True
        assert "exact real numbers" in r.domain

    def test_float_literal_and_true_division(self):
        r = verify_function_equivalence(
            "def f(x: float):\n    return x / 2\n", "f",
            "def g(x: float):\n    return x * 0.5\n", "g")
        assert r.equivalent is True

    def test_float_list_elements(self):
        a = "def f(xs: list[float]):\n    return xs[0] if len(xs) > 0 else 0.0\n"
        b = "def g(xs: list[float]):\n    return 0.0 if len(xs) == 0 else xs[0]\n"
        assert verify_function_equivalence(a, "f", b, "g").equivalent is True

    def test_optional_float(self):
        r = simplify_function(
            "def f(x: Optional[float]):\n    return 0.0 if x is None else x\n", "f")
        assert r.status in ("simplified", "already_simplest")


class TestAnnotationsStillRejected:

    def test_any_is_rejected(self):
        """Any admits every type, so there is no sort to model. Rejected."""
        r = simplify_function("def f(x: Any):\n    return x\n", "f")
        assert r.status == "unsupported"

    def test_class_name_is_rejected(self):
        """A class brings methods, properties and aliasing, which this model does not
        represent. Rejected."""
        r = simplify_function("def f(x: Widget):\n    return x\n", "f")
        assert r.status == "unsupported"


class TestZeroDivision:

    def test_unguarded_symbolic_divisor_rejected(self):
        r = simplify_function("def f(x: int, y: int):\n    return x / y\n", "f")
        assert r.status == "unsupported"
        assert "may be zero" in r.reason

    def test_guarded_divisor_accepted(self):
        src = "def f(x: int, y: int):\n    if y != 0:\n        return x / y\n    return 0\n"
        r = simplify_function(src, "f")
        assert r.status in ("simplified", "already_simplest"), r.summary()
        for y in GRID:
            if y != 0:
                assert _py(src, "f", 3, y) == 3 / y

    def test_constant_zero_divisor_rejected(self):
        assert simplify_function("def f(x):\n    return 1 / 0\n", "f").status == "unsupported"

    def test_literal_divisor_needs_no_guard(self):
        assert simplify_function("def f(x):\n    return x / 2\n", "f").status in (
            "simplified", "already_simplest")

    def test_try_catches_zero_division(self):
        a = ("def f(x: int, y: int):\n    try:\n        return x / y\n"
             "    except ZeroDivisionError:\n        return 0\n")
        b = "def g(x: int, y: int):\n    return 0 if y == 0 else x / y\n"
        r = verify_function_equivalence(a, "f", b, "g")
        assert r.equivalent is True, r.summary()
        for y in GRID:
            assert _py(a, "f", 3, y) == _py(b, "g", 3, y)

    def test_uncaught_zero_division_is_excluded_and_noted(self):
        src = ("def f(x: int, y: int):\n    try:\n        return x / y\n"
               "    except IndexError:\n        return 0\n")
        r = simplify_function(src, "f")
        assert r.status in ("simplified", "already_simplest")
        assert "exception the handler does not catch" in r.domain




class TestUnusedParameters:

    def test_unused_unmodelled_parameter_is_ignored(self):
        r = simplify_function("def f(x: int, cfg: Any):\n    return x + 0\n", "f")
        assert r.status in ("simplified", "already_simplest"), r.summary()

    def test_used_unmodelled_parameter_is_rejected(self):
        r = simplify_function("def f(x: int, cfg: set[str]):\n    return cfg\n", "f")
        assert r.status == "unsupported"
        assert "Any value" in r.reason  # an unmodelled type is opaque, and returning it is rejected

    def test_unused_class_parameter_is_ignored(self):
        r = verify_function_equivalence(
            "def f(x: int, w: Widget):\n    return x\n", "f",
            "def g(x: int, w: Any):\n    return x\n", "g")
        assert r.equivalent is True
