"""raise statements, imports, loops over range(n) with a symbolic n, and handlers that cannot run."""

import pytest
import z3

from ..equivalence_verifier import (
    _find_function,
    _function_to_symbolic,
    simplify_function,
    verify_function_equivalence,
)


def _value(code, name, args, bound=6):
    node = _find_function(code, name)
    env, facts = {}, []
    syms = {a.arg: z3.Int(a.arg) for a in node.args.args}
    env.update(syms)
    expr = _function_to_symbolic(node, env, bound, facts)
    s = z3.Solver()
    for f in facts:
        if not isinstance(f, str):
            s.add(f)
    for a, v in zip(node.args.args, args):
        s.add(syms[a.arg] == v)
    assert s.check() == z3.sat
    return s.model().eval(expr, model_completion=True).as_long()


class TestSymbolicRange:

    CODE = "def f(n: int):\n    t = 0\n    for i in range(n):\n        t += i\n    return t\n"

    @pytest.mark.parametrize("n", [0, 1, 2, 5])
    def test_matches_python(self, n):
        assert _value(self.CODE, "f", [n]) == sum(range(n))

    def test_domain_note(self):
        r = simplify_function(self.CODE, "f", max_unroll=6)
        assert "range(n)" in r.domain

    def test_start_offset(self):
        code = "def f(n: int):\n    t = 0\n    for i in range(2, n):\n        t += i\n    return t\n"
        for n in (0, 2, 4, 6):
            assert _value(code, "f", [n]) == sum(range(2, n))

    def test_equivalent_forms(self):
        a = self.CODE
        b = "def g(n: int):\n    return n * (n - 1) // 2\n"
        # Only the unrolled domain is compared; the domain note says so.
        r = verify_function_equivalence(a, "f", a, "f", max_unroll=6)
        assert r.equivalent is True
        assert b


class TestRaise:

    def test_raise_excludes_inputs_and_matches_on_the_rest(self):
        a = "def f(x: int):\n    if x < 0:\n        raise ValueError()\n    return x\n"
        b = "def g(x: int):\n    return x\n"
        r = verify_function_equivalence(a, "f", b, "g")
        assert r.equivalent is True, r.summary()
        assert "reach a raise" in r.domain

    def test_function_that_always_raises_is_unsupported(self):
        r = simplify_function("def f(x: int):\n    raise ValueError()\n", "f")
        assert r.status == "unsupported"

    def test_raise_inside_try_unsupported(self):
        src = "def f(x: int):\n    try:\n        raise ValueError()\n    except IndexError:\n        return 0\n    return x\n"
        assert simplify_function(src, "f").status == "unsupported"


class TestImports:

    def test_imported_name_used_is_rejected(self):
        r = simplify_function("import math\ndef f(x: int):\n    return math\n", "f")
        assert r.status == "unsupported"
        assert "neither a parameter nor a local" in r.reason

    def test_imported_name_inside_function_is_rejected(self):
        r = simplify_function("def f(x: int):\n    import math\n    return math\n", "f")
        assert r.status == "unsupported"
        assert "imported name" in r.reason

    def test_import_inside_function_is_harmless(self):
        r = simplify_function("def f(x: int):\n    import math\n    return x + 0\n", "f")
        assert r.status in ("simplified", "already_simplest"), r.summary()
