"""
Tests for pyprover/z3_builtins.py.

Covers: len()/abs()/min()/max() as real Z3 arithmetic (not silently
skipped), string predicates backed by real Z3 String theory, the
string-typing inference pre-pass, and the honest unsupported boundary
(unknown function names, method calls, wrong arg counts all fall through
to None rather than crashing or guessing).
"""

import pytest
import z3

from ..z3_builtins import try_call_to_z3, infer_string_names, seed_string_env
from ..contract_verifier import _expr_to_z3
import ast


def _call_node(expr: str) -> ast.Call:
    return ast.parse(expr, mode="eval").body


class TestLenAbsMinMax:

    def test_len_returns_consistent_var_for_repeated_calls(self):
        env = {}
        a = try_call_to_z3(_call_node("len(arr)"), env, _expr_to_z3)
        b = try_call_to_z3(_call_node("len(arr)"), env, _expr_to_z3)
        assert a is b  # same Z3 AST object, not just equal

    def test_len_different_args_get_different_vars(self):
        env = {}
        a = try_call_to_z3(_call_node("len(arr)"), env, _expr_to_z3)
        b = try_call_to_z3(_call_node("len(other)"), env, _expr_to_z3)
        s = z3.Solver()
        s.add(a == 3, b == 5)
        assert s.check() == z3.sat  # independent variables, no forced coupling

    def test_abs_real_semantics(self):
        env = {'x': z3.Int('x')}
        result = try_call_to_z3(_call_node("abs(x)"), env, _expr_to_z3)
        s = z3.Solver()
        s.add(env['x'] == -5)
        s.add(result != 5)
        assert s.check() == z3.unsat  # abs(-5) must be 5, no other model

    def test_min_max_real_semantics(self):
        env = {'a': z3.Int('a'), 'b': z3.Int('b')}
        mn = try_call_to_z3(_call_node("min(a, b)"), env, _expr_to_z3)
        mx = try_call_to_z3(_call_node("max(a, b)"), env, _expr_to_z3)
        s = z3.Solver()
        s.add(env['a'] == 3, env['b'] == 7)
        s.add(z3.Or(mn != 3, mx != 7))
        assert s.check() == z3.unsat

    def test_min_variadic(self):
        env = {'a': z3.Int('a'), 'b': z3.Int('b'), 'c': z3.Int('c')}
        result = try_call_to_z3(_call_node("min(a, b, c)"), env, _expr_to_z3)
        s = z3.Solver()
        s.add(env['a'] == 5, env['b'] == 1, env['c'] == 9)
        s.add(result != 1)
        assert s.check() == z3.unsat


class TestStringPredicates:

    def test_str_length_real(self):
        env = {'s': z3.String('s')}
        result = try_call_to_z3(_call_node('str_length(s)'), env, _expr_to_z3)
        s = z3.Solver()
        s.add(env['s'] == z3.StringVal("hello"))
        s.add(result != 5)
        assert s.check() == z3.unsat

    def test_str_contains_real(self):
        env = {'s': z3.String('s')}
        result = try_call_to_z3(_call_node('str_contains(s, "wor")'), env, _expr_to_z3)
        s = z3.Solver()
        s.add(env['s'] == z3.StringVal("hello world"))
        s.add(z3.Not(result))
        assert s.check() == z3.unsat  # "hello world" definitely contains "wor"

    def test_str_contains_can_be_false(self):
        env = {'s': z3.String('s')}
        result = try_call_to_z3(_call_node('str_contains(s, "xyz")'), env, _expr_to_z3)
        s = z3.Solver()
        s.add(env['s'] == z3.StringVal("hello world"))
        s.add(result)
        assert s.check() == z3.unsat  # "hello world" definitely does NOT contain "xyz"

    def test_str_starts_with_real(self):
        env = {'s': z3.String('s')}
        result = try_call_to_z3(_call_node('str_starts_with(s, "hel")'), env, _expr_to_z3)
        s = z3.Solver()
        s.add(env['s'] == z3.StringVal("hello"))
        s.add(z3.Not(result))
        assert s.check() == z3.unsat

    def test_str_equals_uses_real_string_equality(self):
        env = {'a': z3.String('a'), 'b': z3.String('b')}
        result = try_call_to_z3(_call_node('str_equals(a, b)'), env, _expr_to_z3)
        s = z3.Solver()
        s.add(env['a'] == z3.StringVal("x"))
        s.add(env['b'] == z3.StringVal("y"))
        s.add(result)
        assert s.check() == z3.unsat  # "x" != "y", str_equals must be false

    def test_str_length_on_int_returns_none_not_crash(self):
        """str_length applied to something that resolves to an Int (wrong
        type) must degrade to None, not raise or silently misassert."""
        env = {'n': z3.Int('n')}
        result = try_call_to_z3(_call_node('str_length(n)'), env, _expr_to_z3)
        assert result is None


class TestUnsupportedBoundary:

    def test_unknown_function_name_returns_none(self):
        env = {}
        assert try_call_to_z3(_call_node("sorted(x)"), env, _expr_to_z3) is None

    def test_method_call_returns_none_not_crash(self):
        env = {}
        assert try_call_to_z3(_call_node('x.upper()'), env, _expr_to_z3) is None

    def test_wrong_arg_count_returns_none(self):
        env = {}
        assert try_call_to_z3(_call_node("len(a, b)"), env, _expr_to_z3) is None
        assert try_call_to_z3(_call_node("min(a)"), env, _expr_to_z3) is None

    def test_z3_unavailable_returns_none(self, monkeypatch):
        from .. import z3_builtins as zbmod
        monkeypatch.setattr(zbmod, "Z3_AVAILABLE", False)
        assert try_call_to_z3(_call_node("len(x)"), {}, _expr_to_z3) is None


class TestStringTypeInference:

    def test_infers_from_literal_comparison(self):
        assert infer_string_names(['s == "hello"']) == {'s'}

    def test_infers_from_reversed_literal_comparison(self):
        assert infer_string_names(['"hello" == s']) == {'s'}

    def test_infers_from_str_call_first_arg(self):
        assert infer_string_names(['str_length(name) > 0']) == {'name'}

    def test_no_signal_infers_nothing(self):
        assert infer_string_names(['x > 0', 'y == z']) == set()

    def test_seed_string_env_does_not_overwrite_existing(self):
        env = {'s': z3.Int('s')}  # already typed as Int by caller
        seed_string_env(['s == "hello"'], env)
        assert env['s'].sort_kind() == z3.Z3_INT_SORT  # left alone

    def test_seed_string_env_creates_string_var(self):
        env = {}
        seed_string_env(['s == "hello"'], env)
        assert env['s'].sort_kind() == z3.Z3_SEQ_SORT
