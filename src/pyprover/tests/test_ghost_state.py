"""
Tests for pyprover/ghost_state.py.

Covers: comment-based extraction (`# Ghost:` / `# GhostUpdate:`), real Z3
consistency checking (both the honest weaker "self-consistent" mode and the
stronger mode when real-variable constraints are actually supplied), a
genuine contradiction being detected as UNSAT (not just always reporting
success), and the unsupported boundary for undeclared/unparseable ghosts.
"""

import pytest
import z3

from ..ghost_state import GhostStateTracker, GhostVariable, GhostUpdate
from ..contract_verifier import _expr_to_z3


class TestExtraction:

    def test_extracts_declaration_and_update(self):
        code = """
def f(n):
    # Ghost: count = 0
    # GhostUpdate: count = count + 1
    return n
"""
        decls, updates = GhostStateTracker.extract(code)
        assert len(decls) == 1 and decls[0].name == "count" and decls[0].initial_expr == "0"
        assert len(updates) == 1 and updates[0].update_expr == "count + 1"

    def test_no_ghost_annotations_returns_empty(self):
        decls, updates = GhostStateTracker.extract("def f(n):\n    return n\n")
        assert decls == [] and updates == []

    def test_line_numbers_recorded(self):
        code = "x = 1\n# Ghost: g = 0\ny = 2\n"
        decls, _ = GhostStateTracker.extract(code)
        assert decls[0].line_number == 2


class TestConsistencyChecking:

    def test_no_declarations_trivially_consistent(self):
        r = GhostStateTracker.check_consistency([], [], {}, _expr_to_z3)
        assert r.consistent is True

    def test_simple_declaration_and_update_consistent(self):
        decls = [GhostVariable(name="count", initial_expr="0")]
        updates = [GhostUpdate(name="count", update_expr="count + 1", line_number=1)]
        r = GhostStateTracker.check_consistency(decls, updates, {}, _expr_to_z3)
        assert r.consistent is True
        assert r.status == "verified"

    def test_weak_mode_disclosed_when_no_real_constraints_given(self):
        decls = [GhostVariable(name="g", initial_expr="0")]
        r = GhostStateTracker.check_consistency(decls, [], {}, _expr_to_z3)
        assert "no real-variable constraints were supplied" in r.detail

    def test_strong_mode_disclosed_when_real_constraints_given(self):
        n = z3.Int('n')
        decls = [GhostVariable(name="g", initial_expr="n")]
        r = GhostStateTracker.check_consistency(
            decls, [], {'n': n}, _expr_to_z3, real_var_constraints=[n > 0],
        )
        assert "jointly satisfiable with 1 real-variable constraint" in r.detail

    def test_genuine_contradiction_detected(self):
        """count == n, n < 0, and a separately-declared ghost forcing
        count >= 0 (via the real constraints list) must be UNSAT -- this is
        a real Z3 check, not a tracker that always reports success."""
        n = z3.Int('n')
        decls = [
            GhostVariable(name="count", initial_expr="n"),
        ]
        real_constraints = [n < 0, z3.Int('count') >= 0]
        r = GhostStateTracker.check_consistency(
            decls, [], {'n': n}, _expr_to_z3, real_var_constraints=real_constraints,
        )
        assert r.consistent is False
        assert r.status == "inconsistent"

    def test_update_referencing_undeclared_ghost_is_unsupported(self):
        updates = [GhostUpdate(name="never_declared", update_expr="1", line_number=1)]
        r = GhostStateTracker.check_consistency([], updates, {}, _expr_to_z3)
        assert r.status == "unsupported"
        assert "undeclared" in r.detail

    def test_unparseable_expression_is_unsupported_not_crash(self):
        decls = [GhostVariable(name="g", initial_expr="this is not : valid python (((")]
        r = GhostStateTracker.check_consistency(decls, [], {}, _expr_to_z3)
        assert r.status == "unsupported"

    def test_z3_unavailable_reports_unsupported(self, monkeypatch):
        from .. import ghost_state as gmod
        monkeypatch.setattr(gmod, "Z3_AVAILABLE", False)
        decls = [GhostVariable(name="g", initial_expr="0")]
        r = GhostStateTracker.check_consistency(decls, [], {}, _expr_to_z3)
        assert r.status == "unsupported"
