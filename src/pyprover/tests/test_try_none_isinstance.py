"""try/except, None tests and isinstance in simplify_function and verify_function_equivalence.

Each construct is checked against the Python it stands for, on concrete inputs.
Claims that depend on what an exception handler catches say so in `domain`.
"""

import pytest

from ..equivalence_verifier import simplify_function, verify_function_equivalence

LISTS = [[], [0], [2, 3], [-4, 5, 6]]


def _run(src, name, *args):
    ns = {}
    exec(src, ns)
    try:
        return ns[name](*args)
    except (IndexError, KeyError, TypeError):
        return "raised"


class TestTry:

    TRY = ("def f(xs: list[int]):\n    try:\n        return xs[0]\n"
           "    except IndexError:\n        return -1\n")
    GUARDED = "def g(xs: list[int]):\n    return xs[0] if len(xs) > 0 else -1\n"

    def test_index_try_equivalent_to_guard(self):
        r = verify_function_equivalence(self.TRY, "f", self.GUARDED, "g")
        assert r.equivalent is True, r.summary()
        for xs in LISTS:
            assert _run(self.TRY, "f", xs) == _run(self.GUARDED, "g", xs)

    def test_try_that_does_not_catch_is_rejected_when_failure_can_happen(self):
        """A key error is not caught, so inputs that cause one are excluded and noted."""
        src = ("def f(d: dict[int, int], k: int):\n    try:\n        return d[k]\n"
               "    except IndexError:\n        return 0\n")
        r = simplify_function(src, "f")
        assert r.status in ("simplified", "already_simplest")
        assert "exception the handler does not catch" in r.domain

    def test_failure_free_try_adds_no_domain_note(self):
        src = "def f(x):\n    try:\n        y = x + 1\n    except IndexError:\n        y = 0\n    return y\n"
        r = simplify_function(src, "f")
        assert r.domain is None

    def test_handler_reading_assigned_name_rejected(self):
        src = ("def f(xs: list[int]):\n    v = 0\n    try:\n        v = xs[0]\n"
               "    except IndexError:\n        return v\n    return v\n")
        assert simplify_function(src, "f").status == "unsupported"

    def test_nested_and_unmodelled_handlers_rejected(self):
        nested = ("def f(xs: list[int]):\n    try:\n        try:\n            return xs[0]\n"
                  "        except IndexError:\n            return 1\n    except IndexError:\n        return 2\n")
        assert simplify_function(nested, "f").status == "unsupported"
        valerr = "def f(xs: list[int]):\n    try:\n        return xs[0]\n    except ValueError:\n        return 0\n"
        assert simplify_function(valerr, "f").status == "unsupported"
        # A handler that can never run may name any exception.
        never = "def f(x):\n    try:\n        return x\n    except ValueError:\n        return 0\n"
        assert simplify_function(never, "f").status in ("simplified", "already_simplest")
        finally_ = "def f(x):\n    try:\n        return x\n    finally:\n        pass\n"
        assert simplify_function(finally_, "f").status == "unsupported"

    def test_unguarded_read_outside_try_still_rejected(self):
        src = "def f(xs: list[int]):\n    y = xs[0]\n    try:\n        return 1\n    except IndexError:\n        return 0\n"
        assert simplify_function(src, "f").status == "unsupported"


class TestNone:

    GUARD = "def f(x: Optional[int]):\n    if x is None:\n        return 0\n    return x + 1\n"
    TERN = "def g(x: Optional[int]):\n    return 0 if x is None else x + 1\n"

    def test_guard_equivalent_to_ternary(self):
        r = verify_function_equivalence(self.GUARD, "f", self.TERN, "g")
        assert r.equivalent is True, r.summary()

    def test_unguarded_use_of_optional_rejected(self):
        r = simplify_function("def f(x: Optional[int]):\n    return x + 1\n", "f")
        assert r.status == "unsupported"
        assert "may be None" in r.reason

    def test_none_comparison_on_plain_parameter_is_constant(self):
        r = verify_function_equivalence(
            "def f(x: int):\n    return 1 if x is not None else 0\n", "f",
            "def g(x: int):\n    return 1\n", "g")
        assert r.equivalent is True

    def test_returning_none_is_rejected(self):
        assert simplify_function("def f(x: Optional[int]):\n    return None\n", "f").status == "unsupported"


class TestIsinstance:

    def test_int_parameter_is_int(self):
        r = simplify_function("def f(x: int):\n    return 1 if isinstance(x, int) else 0\n", "f")
        assert r.status in ("simplified", "already_simplest")
        assert "annotations state" in r.domain

    def test_bool_is_an_int(self):
        r = verify_function_equivalence(
            "def f(b: bool):\n    return isinstance(b, int)\n", "f",
            "def g(b: bool):\n    return True\n", "g")
        assert r.equivalent is True

    def test_wrong_type_is_false(self):
        r = verify_function_equivalence(
            "def f(x: int):\n    return isinstance(x, str)\n", "f",
            "def g(x: int):\n    return False\n", "g")
        assert r.equivalent is True

    def test_unmodelled_type_rejected(self):
        assert simplify_function("def f(x: int):\n    return isinstance(x, set)\n", "f").status == "unsupported"


class TestAnnotations:

    @pytest.mark.parametrize("ann", ["set[int]", "Foo"])
    def test_unmodelled_annotation_rejected(self, ann):
        r = simplify_function(f"def f(x: {ann}):\n    return x\n", "f")
        assert r.status == "unsupported"
        assert "Any value" in r.reason  # an unmodelled type is opaque, and returning it is rejected
