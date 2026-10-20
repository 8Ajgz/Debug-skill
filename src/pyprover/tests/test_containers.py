"""simplify_function / verify_function_equivalence over list[int] and dict[int, int].

The key property: a read is only translated where the solver proves it cannot
fail, so an equivalence claim never covers an input where Python would raise.
Claims are also checked by running the original Python on concrete inputs.
"""

import itertools

import pytest

from ..equivalence_verifier import (
    simplify_function,
    verify_function_equivalence,
)

LISTS = [[], [0], [1], [2, 3], [-4, 5, 6], [7, -1, 2, 9]]
DICTS = [{}, {0: 1}, {2: -3}, {0: 5, 1: 6, 4: 7}]


def _same_result(f, g, args):
    """Compare f and g on one input; a raise in either is not a comparison."""
    try:
        a = f(*args)
    except (IndexError, KeyError):
        a = "raised"
    try:
        b = g(*args)
    except (IndexError, KeyError):
        b = "raised"
    return a, b


def _check_claim_on_inputs(a_src, a_name, b_src, b_name, inputs):
    ns_a, ns_b = {}, {}
    exec(a_src, ns_a)
    exec(b_src, ns_b)
    for args in inputs:
        a, b = _same_result(ns_a[a_name], ns_b[b_name], args)
        if a == "raised" or b == "raised":
            assert a == b, f"{args}: one side raises, the other returns ({a!r}, {b!r})"
        else:
            assert a == b, f"{args}: {a!r} != {b!r}"


class TestListReads:

    GUARDED = "def f(xs: list[int]):\n    if len(xs) > 0:\n        return xs[0]\n    return 0\n"
    TERNARY = "def g(xs: list[int]):\n    return xs[0] if len(xs) > 0 else 0\n"

    def test_guarded_read_equivalent_to_ternary(self):
        r = verify_function_equivalence(self.GUARDED, "f", self.TERNARY, "g")
        assert r.equivalent is True
        _check_claim_on_inputs(self.GUARDED, "f", self.TERNARY, "g", [(x,) for x in LISTS])

    def test_unguarded_read_is_unsupported(self):
        r = simplify_function("def f(xs: list[int]):\n    return xs[0]\n", "f")
        assert r.status == "unsupported"
        assert "may fail" in r.reason

    def test_negative_index_matches_python(self):
        a = "def f(xs: list[int]):\n    if len(xs) > 0:\n        return xs[-1]\n    return 0\n"
        b = "def g(xs: list[int]):\n    if len(xs) > 0:\n        return xs[len(xs) - 1]\n    return 0\n"
        r = verify_function_equivalence(a, "f", b, "g")
        assert r.equivalent is True
        _check_claim_on_inputs(a, "f", b, "g", [(x,) for x in LISTS])

    def test_index_bounds_both_sides_checked(self):
        """xs[len(xs)] is out of range even when the list is non-empty."""
        code = "def f(xs: list[int]):\n    if len(xs) > 0:\n        return xs[len(xs)]\n    return 0\n"
        r = simplify_function(code, "f")
        assert r.status == "unsupported"

    def test_wrong_claim_is_not_proven(self):
        a = "def f(xs: list[int]):\n    if len(xs) > 0:\n        return xs[0]\n    return 0\n"
        b = "def g(xs: list[int]):\n    if len(xs) > 0:\n        return xs[-1]\n    return 0\n"
        r = verify_function_equivalence(a, "f", b, "g")
        assert r.equivalent is not True

    def test_read_in_both_branches_of_a_guard(self):
        code = (
            "def f(xs: list[int]):\n"
            "    if len(xs) == 0:\n"
            "        return -1\n"
            "    return xs[0] + xs[-1]\n"
        )
        r = simplify_function(code, "f")
        assert r.status in ("simplified", "already_simplest")
        _check_claim_on_inputs(
            code, "f",
            "def g(xs):\n    return -1 if len(xs) == 0 else xs[0] + xs[-1]\n", "g",
            [(x,) for x in LISTS],
        )


class TestListLiterals:

    def test_literal_read_folds_to_constant(self):
        a = "def f(x):\n    ys = [1, 2, 3]\n    return ys[1] + len(ys)\n"
        r = verify_function_equivalence(a, "f", "def g(x):\n    return 5\n", "g")
        assert r.equivalent is True

    def test_literal_out_of_range_is_unsupported(self):
        r = simplify_function("def f(x):\n    ys = [1]\n    return ys[1]\n", "f")
        assert r.status == "unsupported"


class TestRejectedUses:

    @pytest.mark.parametrize("code", [
        "def f(xs: list[int]):\n    xs[0] = 1\n    return xs[0]\n",
        "def f(xs: list[int]):\n    xs.append(1)\n    return 0\n",
        "def f(xs: list[int]):\n    ys = xs\n    return 0\n",
        "def f(xs: list[int]):\n    return xs\n",
        "def f(xs: list[int], x: int):\n    return x in xs\n",
        "def f(xs: list[int]):\n    return len(xs) + len(xs[0:1])\n",
    ])
    def test_writes_aliases_and_values_rejected(self, code):
        r = simplify_function(code, "f")
        assert r.status == "unsupported", r.summary()

    def test_reserved_temporary_name_rejected(self):
        r = simplify_function("def f(x):\n    __c0 = 1\n    return __c0\n", "f")
        assert r.status == "unsupported"


class TestDictReads:

    GUARDED = "def f(d: dict[int, int], k: int):\n    if k in d:\n        return d[k]\n    return 0\n"
    TERNARY = "def g(d: dict[int, int], k: int):\n    return d[k] if k in d else 0\n"

    def test_guarded_lookup_equivalent_to_ternary(self):
        r = verify_function_equivalence(self.GUARDED, "f", self.TERNARY, "g")
        assert r.equivalent is True
        _check_claim_on_inputs(
            self.GUARDED, "f", self.TERNARY, "g",
            [(d, k) for d in DICTS for k in range(-1, 5)],
        )

    def test_unguarded_lookup_is_unsupported(self):
        r = simplify_function("def f(d: dict[int, int], k: int):\n    return d[k]\n", "f")
        assert r.status == "unsupported"

    def test_not_in_guard(self):
        a = "def f(d: dict[int, int], k: int):\n    if k not in d:\n        return 0\n    return d[k]\n"
        r = verify_function_equivalence(a, "f", self.TERNARY, "g")
        assert r.equivalent is True
        _check_claim_on_inputs(
            a, "f", self.TERNARY, "g",
            [(d, k) for d in DICTS for k in range(-1, 5)],
        )

    def test_len_of_dict_unsupported(self):
        r = simplify_function("def f(d: dict[int, int]):\n    return len(d)\n", "f")
        assert r.status == "unsupported"


class TestParameterKinds:

    def test_list_versus_dict_parameter_rejected(self):
        a = "def f(xs: list[int]):\n    return 0\n"
        b = "def g(d: dict[int, int]):\n    return 0\n"
        r = verify_function_equivalence(a, "f", b, "g")
        assert r.status == "unsupported"
        assert "parameter types differ" in r.reason

    def test_branch_merge_of_container_values(self):
        """A branch that rebinds a name to a different container is merged by
        choosing between its arrays, which is sound. Here the rebinding is a
        list literal on one side and the parameter on the other, so it is rejected."""
        code = (
            "def f(xs: list[int], c: bool):\n"
            "    if c:\n"
            "        ys = [1]\n"
            "    else:\n"
            "        ys = xs\n"
            "    return 0\n"
        )
        r = simplify_function(code, "f")
        assert r.status == "unsupported"


class TestShortCircuit:

    @pytest.mark.parametrize("code", [
        "def f(xs: list[int]):\n    return len(xs) > 0 and xs[0] > 0\n",
        "def f(xs: list[int]):\n    return len(xs) == 0 or xs[0] > 0\n",
    ])
    def test_guarded_operand_is_accepted(self, code):
        r = simplify_function(code, "f")
        assert r.status in ("simplified", "already_simplest"), r.summary()

    def test_unguarded_operand_is_rejected(self):
        r = simplify_function("def f(xs: list[int]):\n    return xs[0] > 0 and len(xs) > 0\n", "f")
        assert r.status == "unsupported"

    def test_guard_claim_matches_python_on_inputs(self):
        a = "def f(xs: list[int]):\n    return len(xs) > 0 and xs[0] > 0\n"
        b = "def g(xs: list[int]):\n    if len(xs) == 0:\n        return False\n    return xs[0] > 0\n"
        r = verify_function_equivalence(a, "f", b, "g")
        assert r.equivalent is True
        _check_claim_on_inputs(a, "f", b, "g", [(x,) for x in LISTS])

    def test_conditional_expression_branch_guard(self):
        bad = "def f(xs: list[int]):\n    return xs[0] if len(xs) > 0 else xs[1]\n"
        r = simplify_function(bad, "f")
        assert r.status == "unsupported"
        good = "def f(xs: list[int]):\n    return xs[0] if len(xs) > 0 else 0\n"
        assert simplify_function(good, "f").status in ("simplified", "already_simplest")


STR_LISTS = [[], ["a"], ["b", "a"], ["a", "c", "a"]]
STR_DICTS = [{}, {"a": 1}, {"b": -2}, {"a": 5, "c": 7}]


class TestStringElements:

    def test_string_list_read_guarded(self):
        a = "def f(xs: list[str]):\n    if len(xs) > 0:\n        return xs[0] == 'a'\n    return False\n"
        b = "def g(xs: list[str]):\n    return len(xs) > 0 and xs[0] == 'a'\n"
        r = verify_function_equivalence(a, "f", b, "g")
        assert r.equivalent is True, r.summary()
        _check_claim_on_inputs(a, "f", b, "g", [(x,) for x in STR_LISTS])

    def test_string_dict_lookup_guarded(self):
        a = "def f(d: dict[str, int], k: str):\n    if k in d:\n        return d[k]\n    return 0\n"
        b = "def g(d: dict[str, int], k: str):\n    return d[k] if k in d else 0\n"
        r = verify_function_equivalence(a, "f", b, "g")
        assert r.equivalent is True, r.summary()
        _check_claim_on_inputs(a, "f", b, "g", [(d, k) for d in STR_DICTS for k in ["a", "b", "z"]])

    def test_unguarded_string_read_unsupported(self):
        r = simplify_function("def f(xs: list[str]):\n    return xs[0]\n", "f")
        assert r.status == "unsupported"

    def test_mixed_list_literal_rejected(self):
        r = simplify_function("def f(x):\n    ys = [1, 'a']\n    return 0\n", "f")
        assert r.status == "unsupported"
