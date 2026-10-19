"""Tests for SMT-LIB export: each script must give the same verdict when re-solved."""
import pytest

from ..contract_verifier import Z3_AVAILABLE, ContractVerifier
from ..smtlib_export import export_smtlib

pytestmark = pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver not installed")

PROVABLE = "# Pre: x > 100\n# Post: x > 0\ndef f(x):\n    return x\n"
NOT_IMPLIED = "# Pre: x > 0\n# Post: x < 0\ndef g(x):\n    return x\n"
RESULT_CLAUSE = "# Pre: x > 0\n# Post: result > 0\ndef h(x):\n    return x\n"


def _solve(smt2: str) -> str:
    import z3
    solver = z3.Solver()
    solver.from_string(smt2)
    return str(solver.check())


@pytest.mark.verification
class TestExportSmtlib:
    def test_one_script_per_postcondition(self):
        scripts = export_smtlib(PROVABLE)
        assert len(scripts) == 1
        assert scripts[0]["clause"] == "x > 0"
        assert scripts[0]["check"] == "implication"
        assert scripts[0]["expected"] == "unsat"

    def test_script_is_smtlib_with_check_sat(self):
        smt2 = export_smtlib(PROVABLE)[0]["smt2"]
        assert "(check-sat)" in smt2
        assert "(assert" in smt2

    def test_implied_postcondition_is_unsat_when_resolved(self):
        script = export_smtlib(PROVABLE)[0]
        assert _solve(script["smt2"]) == script["expected"] == "unsat"

    def test_not_implied_postcondition_is_sat_when_resolved(self):
        script = export_smtlib(NOT_IMPLIED)[0]
        assert _solve(script["smt2"]) == "sat"

    def test_export_agrees_with_verify_contract(self):
        for code in (PROVABLE, NOT_IMPLIED):
            script = export_smtlib(code)[0]
            solver_says_verified = _solve(script["smt2"]) == script["expected"]
            assert solver_says_verified == ContractVerifier.verify_contract(code)["verified"]

    def test_result_clause_uses_satisfiability(self):
        script = export_smtlib(RESULT_CLAUSE)[0]
        assert script["check"] == "satisfiability"
        assert script["expected"] == "sat"
        assert _solve(script["smt2"]) == "sat"

    def test_no_postconditions_no_scripts(self):
        assert export_smtlib("# Pre: x > 0\ndef f(x):\n    return x\n") == []
