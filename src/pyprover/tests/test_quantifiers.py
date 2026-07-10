"""
Tests for pyprover/quantifiers.py.

Covers: forall/exists parsing, bounded-unroll verification and violation
(with real counterexamples), native Z3 quantifier strategy for symbolic
bounds, and the honest unsupported/skip boundary.
"""

import pytest
import z3

from ..quantifiers import try_parse_quantifier, check_quantifier, MAX_UNROLL
from ..contract_verifier import _expr_to_z3


class TestParsing:

    def test_forall_parses(self):
        c = try_parse_quantifier("all(i >= 0 for i in range(0, 10))")
        assert c is not None
        assert c.kind == "forall"
        assert c.bound_var == "i"
        assert c.lo_expr == "0" and c.hi_expr == "10"

    def test_exists_parses(self):
        c = try_parse_quantifier("any(i == 7 for i in range(0, 10))")
        assert c.kind == "exists"

    def test_single_arg_range_defaults_lo_to_zero(self):
        c = try_parse_quantifier("all(i >= 0 for i in range(10))")
        assert c.lo_expr == "0" and c.hi_expr == "10"

    def test_non_quantifier_returns_none(self):
        assert try_parse_quantifier("x + 1 > 0") is None

    def test_step_argument_not_guessed_at(self):
        """range(lo, hi, step) is refused rather than silently ignoring step."""
        assert try_parse_quantifier("all(i >= 0 for i in range(0, 10, 2))") is None

    def test_empty_string_returns_none(self):
        assert try_parse_quantifier("") is None


class TestBoundedUnroll:

    def test_forall_verified(self):
        c = try_parse_quantifier("all(i >= 0 for i in range(0, 10))")
        r = check_quantifier(c, {}, _expr_to_z3)
        assert r.verified is True
        assert r.strategy == "bounded_unroll"
        assert r.instances_checked == 10

    def test_forall_violated_has_real_counterexample(self):
        c = try_parse_quantifier("all(i < 5 for i in range(0, 10))")
        r = check_quantifier(c, {}, _expr_to_z3)
        assert r.verified is False
        assert r.status == "violated"
        assert r.counterexample == "i = 5"

    def test_exists_verified_has_witness(self):
        c = try_parse_quantifier("any(i == 7 for i in range(0, 10))")
        r = check_quantifier(c, {}, _expr_to_z3)
        assert r.verified is True
        assert r.counterexample == "i = 7"

    def test_exists_violated_no_witness_in_range(self):
        c = try_parse_quantifier("any(i == 20 for i in range(0, 10))")
        r = check_quantifier(c, {}, _expr_to_z3)
        assert r.verified is False
        assert r.status == "violated"

    def test_empty_range_forall_vacuously_true(self):
        c = try_parse_quantifier("all(i > 0 for i in range(5, 5))")
        r = check_quantifier(c, {}, _expr_to_z3)
        assert r.verified is True
        assert r.instances_checked == 0


class TestNativeZ3Strategy:

    def test_symbolic_bound_uses_native_z3(self):
        """A range bound that isn't a small int literal (a free Z3 variable)
        must fall through to native ForAll, not silently be skipped."""
        n = z3.Int('n')
        c = try_parse_quantifier("all(i >= 0 for i in range(0, n))")
        r = check_quantifier(c, {'n': n}, _expr_to_z3)
        assert r.strategy == "native_z3"
        assert r.verified is True

    def test_large_literal_bound_uses_native_z3_not_unroll(self):
        """A bound larger than MAX_UNROLL must not be unrolled (would be slow
        and defeats the point of having a native strategy at all)."""
        c = try_parse_quantifier(f"all(i >= 0 for i in range(0, {MAX_UNROLL + 1}))")
        r = check_quantifier(c, {}, _expr_to_z3)
        assert r.strategy == "native_z3"


class TestUnsupportedBoundary:

    def test_z3_unavailable_reports_unsupported_not_crash(self, monkeypatch):
        from .. import quantifiers as qmod
        monkeypatch.setattr(qmod, "Z3_AVAILABLE", False)
        c = try_parse_quantifier("all(i >= 0 for i in range(0, 10))")
        r = check_quantifier(c, {}, _expr_to_z3)
        assert r.status == "unsupported"
        assert r.verified is False
