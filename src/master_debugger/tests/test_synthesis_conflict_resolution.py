"""
Tests for MasterDebugger's synthesis/conflict-resolution logic (roadmap.md
§20, closing the gap §5 flagged as missing: master-debugger v3.0's
three-stream blind-spot model with explicit conflict resolution when
streams disagree).

Real bug this closes: report.issues_found only ever contained
async-concurrency findings -- static analysis and runtime-trace findings
were counted into local variables and then discarded, never reaching
report.issues_found. Confirmed directly: code with a real NameError
(captured correctly in the runtime trace) alongside a trivially-true formal
contract produced "✅ VERIFIED" / RiskLevel.LOW, because the synthesis logic
checked report.issues_found (empty) instead of the real total. Fixed by
(a) actually appending static/runtime findings as Issue objects, and
(b) restructuring synthesis to surface an explicit CONFLICT state instead
of letting a passing formal check silently override other streams' findings.
"""

import pytest
import asyncio
from ..orchestrator import MasterDebugger


class TestSynthesisConflictResolution:

    @pytest.fixture
    def debugger(self):
        return MasterDebugger(use_pyprover=True)

    def test_clean_code_still_verifies(self, debugger):
        """The common, correct case must still work: no static/runtime
        issues, formal contract passes -> genuine VERIFIED."""
        code = """
def add(a: int, b: int) -> int:
    # Pre: True
    # Post: result == a + b
    return a + b
"""
        report = asyncio.run(debugger.debug_comprehensive(code, language="python"))
        assert report.overall_health == "✅ VERIFIED"
        assert report.risk_level.name == "LOW"

    def test_runtime_crash_with_unprovable_contract_is_not_verified(self, debugger):
        """A real runtime crash must not be hidden by a contract. This body has
        more than one statement, so PyProver cannot prove the postcondition and
        reports inconclusive. The crash must still be the verdict's driver."""
        code = """
def add(a: int, b: int) -> int:
    # Pre: True
    # Post: result == a + b
    undefined_variable_reference_xyz
    return a + b

result = add(1, 2)
"""
        report = asyncio.run(debugger.debug_comprehensive(code, language="python"))
        # The return path is fine, and a NameError is a raise, not a return, so
        # PyProver may verify the contract. The crash must still be reported.
        assert report.overall_health != "✅ VERIFIED"
        assert "unhandled_exception" in [i.type for i in report.issues_found]
        assert report.risk_level.name == "HIGH"

    def test_conflict_case_issue_is_actually_populated(self, debugger):
        """report.issues_found must actually contain the runtime finding,
        not just be reflected in a discarded local counter."""
        code = """
def add(a: int, b: int) -> int:
    # Pre: True
    # Post: result == a + b
    undefined_variable_reference_xyz
    return a + b

result = add(1, 2)
"""
        report = asyncio.run(debugger.debug_comprehensive(code, language="python"))
        assert len(report.issues_found) > 0
        assert any(str(i.type) == "unhandled_exception" for i in report.issues_found)
        # severity must be "high" specifically for unhandled_exception, not
        # the enum-vs-string comparison bug that silently produced "medium"
        # for every runtime pattern during development of this fix
        unhandled = [i for i in report.issues_found if str(i.type) == "unhandled_exception"]
        assert unhandled[0].severity == "high"

    def test_runtime_issue_with_no_contract_is_not_verified(self, debugger):
        """Code with zero # Pre:/# Post: annotations used to get verified=True
        from PyProver, which is a vacuous pass. It is now INCONCLUSIVE, so a
        runtime crash here surfaces as an issue and nothing reads as VERIFIED."""
        code = """
def f():
    undefined_name_here
    return 1

f()
"""
        report = asyncio.run(debugger.debug_comprehensive(code, language="python"))
        assert report.pyprover_result.get("verified") is False
        assert report.overall_health != "✅ VERIFIED"
        assert len(report.issues_found) > 0

    def test_both_streams_agree_issues_found_no_conflict_wording(self, debugger):
        """When PyProver's own contract genuinely fails (not just absent)
        AND a runtime/static issue is found, both streams agree something
        is wrong -- this should read as plain "issue(s) found", not
        CONFLICT, since there's no disagreement to surface. Uses mutually
        contradictory preconditions rather than a result-referencing
        postcondition, since ContractVerifier only satisfiability-checks
        (not implication-checks) postconditions that reference `result` --
        a documented pre-existing scope limit, not something to route
        around with a weaker test."""
        code = """
def f(n):
    # Pre: n > 0
    # Pre: n < 0
    undefined_name_here
    return n

f(1)
"""
        report = asyncio.run(debugger.debug_comprehensive(code, language="python"))
        assert report.pyprover_result.get("verified") is False
        assert "CONFLICT" not in report.overall_health
        assert "issue" in report.overall_health.lower()
