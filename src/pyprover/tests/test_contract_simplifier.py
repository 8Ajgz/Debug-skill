"""Tests for ContractSimplifier: redundant clause removal, soundness, and output."""

import ast

import pytest
import z3

from .. import z3_builtins
from ..contract_simplifier import (
    ContractSimplifier,
    _clause_to_z3,
    _is_z3_bool,
    simplify_parsed_contract,
)
from ..contract_verifier import seed_real_env


def _requires_implied(orig, simp, env_clauses):
    """Check orig and simp are equivalent as conjunctions of boolean clauses."""
    env = {}
    seed_real_env(env_clauses, env)
    z3_builtins.seed_string_env(env_clauses, env)

    def conj(clauses):
        parsed = [_clause_to_z3(c, env) for c in clauses]
        parsed = [p for p in parsed if p is not None and _is_z3_bool(p)]
        return z3.And(*parsed) if parsed else z3.BoolVal(True)

    s = z3.Solver()
    s.set("timeout", 5000)
    s.add(z3.Not(conj(orig) == conj(simp)))
    return s.check() == z3.unsat


pytestmark = pytest.mark.skipif(
    not __import__("pyprover.contract_simplifier", fromlist=["Z3_AVAILABLE"]).Z3_AVAILABLE,
    reason="z3-solver not installed",
)


class TestDuplicates:

    def test_identical_requires_collapse_to_one(self):
        result = ContractSimplifier().simplify(["n >= 0", "n >= 0"], [])
        assert result.simplified_requires == ["n >= 0"]
        assert result.reduction_count == 1

    def test_identical_ensures_collapse_to_one(self):
        result = ContractSimplifier().simplify([], ["result > 0", "result > 0"])
        assert result.simplified_ensures == ["result > 0"]
        assert result.reduction_count == 1

    def test_three_copies_collapse_to_one(self):
        result = ContractSimplifier().simplify(["x > 0", "x > 0", "x > 0"], [])
        assert result.simplified_requires == ["x > 0"]


class TestUnsupportedVersusTimeout:

    def test_bare_identifier_ensures_reported_as_unsupported(self):
        result = ContractSimplifier().simplify(["n >= 0"], ["result"])
        assert "result" in result.simplified_ensures
        assert result.unsupported_clauses == ["result"]
        assert "result" not in result.timeout_clauses

    def test_summary_labels_unsupported_clauses_honestly(self):
        result = ContractSimplifier().simplify(["n >= 0"], ["result"])
        summary = result.summary()
        assert "Z3 timeout" not in summary
        assert "not checked" in summary.lower()


def _parse_decorators(text):
    """Parse the decorator block back into (name, clause) pairs."""
    tree = ast.parse(text + "\ndef f(): pass")
    return [(d.func.id, d.args[0].value) for d in tree.body[0].decorator_list]


class TestDecoratorOutput:

    def test_clause_with_double_quotes_round_trips(self):
        result = ContractSimplifier().simplify(['s == "a"'], [])
        assert _parse_decorators(result.as_decorators()) == [("requires", 's == "a"')]

    def test_no_contracts_output(self):
        result = ContractSimplifier().simplify([], [])
        assert result.as_decorators() == "# No contracts required"

    def test_decorators_round_trip_simplified_clauses(self):
        result = ContractSimplifier().simplify(["n >= 0", "n >= 5"], ["result > 0"])
        assert _parse_decorators(result.as_decorators()) == [
            ("requires", "n >= 5"),
            ("ensures", "result > 0"),
        ]


class TestSoundness:

    CASES = [
        (["n >= 0", "n >= 5"], ["result >= 0"]),
        (["x > 0", "x >= 1"], []),
        (["x > 0", "x > 0", "x > 1"], ["result > 0", "result >= 1"]),
        (["x > 0 and y > 0", "x > 0"], ["result > 0"]),
        (["True", "x > 0"], ["x > 0"]),
        (["x == x"], ["result == x"]),
        (["x > 0.5"], ["x > 0.4"]),
        (["n >= 0"], ["if n > 5: result >= 0", "result >= 0"]),
    ]

    @pytest.mark.parametrize("requires,ensures", CASES)
    def test_simplified_contract_is_equivalent(self, requires, ensures):
        result = ContractSimplifier().simplify(requires, ensures)
        everything = requires + ensures
        assert _requires_implied(requires, result.simplified_requires, everything)
        assert _requires_implied(
            requires + ensures,
            result.simplified_requires + result.simplified_ensures,
            everything,
        )

    @pytest.mark.parametrize("requires,ensures", CASES)
    def test_simplify_is_idempotent(self, requires, ensures):
        first = ContractSimplifier().simplify(requires, ensures)
        second = ContractSimplifier().simplify(
            first.simplified_requires, first.simplified_ensures
        )
        assert second.simplified_requires == first.simplified_requires
        assert second.simplified_ensures == first.simplified_ensures

    def test_wrapper_matches_class(self):
        a = simplify_parsed_contract(["n >= 0", "n >= 5"], [])
        b = ContractSimplifier().simplify(["n >= 0", "n >= 5"], [])
        assert a.simplified_requires == b.simplified_requires
