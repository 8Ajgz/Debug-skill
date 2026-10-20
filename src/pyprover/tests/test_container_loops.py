"""Loops over list parameters: exact for lists up to max_unroll, rejected otherwise.

Each result that uses such a loop says so in `domain`, because lists longer
than max_unroll are not covered by the unrolled model.
"""

import ast
import itertools

import pytest
import z3

from ..equivalence_verifier import (
    _find_function,
    _assume_of,
    _function_to_symbolic,
    _make_param,
    _param_kind,
    simplify_function,
    verify_function_equivalence,
)

K = 4
SUM_LOOP = "def f(xs: list[int]):\n    total = 0\n    for x in xs:\n        total += x\n    return total\n"
SUM_INDEX = ("def g(xs: list[int]):\n    total = 0\n    for i in range(len(xs)):\n"
             "        total += xs[i]\n    return total\n")
COUNT_POS = ("def h(xs: list[int]):\n    n = 0\n    for x in xs:\n        if x > 0:\n"
             "            n += 1\n    return n\n")


def _model_value(code, name, args, max_unroll=K):
    """Evaluate the translated function on one concrete list/int input with Z3."""
    node = _find_function(code, name)
    env, facts = {}, []
    symbols = {}
    for arg in node.args.args:
        symbols[arg.arg] = _make_param(_param_kind(arg), arg.arg)
        env[arg.arg] = symbols[arg.arg]
    expr = _function_to_symbolic(node, env, max_unroll, facts)
    s = z3.Solver()
    s.add(_assume_of(facts))
    for arg, value in zip(node.args.args, args):
        sym = symbols[arg.arg]
        if hasattr(sym, "length"):
            s.add(sym.length == len(value))
            for i, v in enumerate(value):
                s.add(z3.Select(sym.items, i) == v)
        else:
            s.add(sym == value)
    assert s.check() == z3.sat
    return s.model().eval(expr, model_completion=True)


class TestEquivalence:

    def test_sum_loop_forms_are_equivalent_with_domain_note(self):
        r = verify_function_equivalence(SUM_LOOP, "f", SUM_INDEX, "g", max_unroll=K)
        assert r.equivalent is True
        assert r.domain == f"lists of length at most {K}"
        assert "lists of length at most" in r.summary()

    def test_different_loops_not_proven_equal(self):
        r = verify_function_equivalence(SUM_LOOP, "f", COUNT_POS, "h", max_unroll=K)
        assert r.equivalent is False


class TestTranslationMatchesPython:

    @pytest.mark.parametrize("xs", [[], [3], [1, -2], [4, 5, 6], [-1, -1, -1, -1]])
    def test_sum_loop(self, xs):
        assert _model_value(SUM_LOOP, "f", [xs]).as_long() == sum(xs)

    @pytest.mark.parametrize("xs", [[], [3], [1, -2], [4, 5, 6, 7], [0, 1, 2, 3]])
    def test_count_loop(self, xs):
        assert _model_value(COUNT_POS, "h", [xs]).as_long() == sum(1 for x in xs if x > 0)

    def test_inputs_longer_than_bound_are_outside_domain(self):
        """With K = 4 a 5-element list is outside the domain: the translation is
        not required to equal the sum, and the fact keeps the solver away from it."""
        node = _find_function(SUM_LOOP, "f")
        env = {"xs": _make_param(("list", "int"), "xs")}
        facts = []
        _function_to_symbolic(node, env, K, facts)
        s = z3.Solver()
        s.add(_assume_of(facts), env["xs"].length == K + 1)
        assert s.check() == z3.unsat


class TestRejected:

    @pytest.mark.parametrize("code", [
        # target read after the loop: may be unbound
        "def f(xs: list[int]):\n    for x in xs:\n        pass\n    return x\n",
        # a name first bound inside the body
        "def f(xs: list[int]):\n    t = 0\n    for x in xs:\n        y = x\n        t += y\n    return t\n",
        # return inside the loop
        "def f(xs: list[int]):\n    for x in xs:\n        return x\n    return 0\n",
        # break and continue
        "def f(xs: list[int]):\n    t = 0\n    for x in xs:\n        break\n    return t\n",
        # iteration over a dict
        "def f(d: dict[int, int]):\n    t = 0\n    for k in d:\n        t += 1\n    return t\n",
        # target must be a simple name
        "def f(xs: list[int]):\n    t = 0\n    for x, y in xs:\n        t += x\n    return t\n",
        # for-else
        "def f(xs: list[int]):\n    t = 0\n    for x in xs:\n        t += x\n    else:\n        t += 1\n    return t\n",
    ])
    def test_rejected(self, code):
        r = simplify_function(code, "f", max_unroll=K)
        assert r.status == "unsupported", r.summary()


class TestGuardedBodies:

    def test_guard_inside_body_matches_python(self):
        for xs in [[], [2], [-1, 3], [1, -2, 3, -4]]:
            assert _model_value(COUNT_POS, "h", [xs]).as_long() == sum(1 for x in xs if x > 0)

    def test_index_read_inside_body_needs_no_extra_guard(self):
        """xs[i] with i < len(xs) is always in range, so the loop body needs no guard."""
        code = ("def f(xs: list[int]):\n    t = 0\n    for i in range(len(xs)):\n"
                "        t += xs[i]\n    return t\n")
        r = simplify_function(code, "f", max_unroll=K)
        assert r.status in ("simplified", "already_simplest"), r.summary()


class TestEmptyAndLiteralMembership:

    def test_empty_list_has_length_zero(self):
        r = verify_function_equivalence(
            "def f(x: int):\n    ys = []\n    return len(ys) + x - x\n", "f",
            "def g(x: int):\n    return 0\n", "g")
        assert r.equivalent is True

    def test_read_from_empty_list_is_guarded_out(self):
        r = simplify_function("def f(x: int):\n    ys = []\n    return ys[0] if len(ys) > 0 else x\n", "f")
        assert r.status in ("simplified", "already_simplest"), r.summary()

    def test_membership_in_literal_list(self):
        a = "def f(x: int):\n    return x in [1, 2, 3]\n"
        b = "def g(x: int):\n    return x == 1 or x == 2 or x == 3\n"
        assert verify_function_equivalence(a, "f", b, "g").equivalent is True

    def test_not_in_empty_literal_is_true(self):
        r = verify_function_equivalence(
            "def f(x: int):\n    return x not in []\n", "f",
            "def g(x: int):\n    return True\n", "g")
        assert r.equivalent is True

    def test_membership_in_literal_list_matches_python(self):
        src = "def f(x: int):\n    return x in [1, 2, 3]\n"
        for x in range(-1, 5):
            assert _model_value(src, "f", [x]) == (x in [1, 2, 3])
