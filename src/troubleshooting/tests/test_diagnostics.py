"""
Tests for troubleshooting/diagnostics.py.

Regression coverage for the STUBS.md DEAD/STUB findings:
- UniversalTroubleshooter._suggest_fixes() used to ignore `state` and
  always return the identical canned result regardless of what was
  diagnosed.
- ToolDiagnostician.diagnose_pyprover_failure() used to always return
  {"suggestions": ["Simplify code"]} regardless of the actual exception.
- HealthChecker.check_all_tools() was hardcoded to report every tool as
  "healthy" unconditionally.

Also confirms the classes are now reachable via `troubleshooting`'s
public `__init__.py` rather than only through a direct, undocumented
import of `diagnostics.py`.

Uses asyncio.run() directly rather than the pytest-asyncio plugin,
which isn't installed in this environment (pytest.ini has
--strict-markers with no asyncio marker registered).
"""

import asyncio

from .. import UniversalTroubleshooter, ToolDiagnostician, HealthChecker


class TestUniversalTroubleshooterRealClassification:
    def test_different_symptoms_get_different_root_causes(self):
        t = UniversalTroubleshooter()

        async def run():
            missing = await t.diagnose_problem("command not found: rustc", tool="rust_debug")
            parse = await t.diagnose_problem("parse error near token", tool="pyprover")
            timeout = await t.diagnose_problem("operation timed out", tool="z3")
            return missing, parse, timeout

        missing, parse, timeout = asyncio.run(run())
        # Previously all three would have returned the identical
        # "Unknown error" / 0.7 confidence regardless of symptom.
        causes = {missing.root_cause, parse.root_cause, timeout.root_cause}
        assert len(causes) == 3
        assert missing.confidence != 0.7 or parse.confidence != 0.7

    def test_missing_dependency_is_auto_fixable(self):
        t = UniversalTroubleshooter()
        result = asyncio.run(t.diagnose_problem("rustc: command not found", tool="rust_debug"))
        assert result.auto_fixable is True

    def test_unclassified_symptom_gets_low_confidence(self):
        t = UniversalTroubleshooter()
        result = asyncio.run(t.diagnose_problem("something weird happened", tool="mystery_tool"))
        assert result.confidence == 0.4


class TestToolDiagnosticianRealExceptionHandling:
    def test_not_implemented_error_gets_specific_suggestion(self):
        d = ToolDiagnostician()
        result = asyncio.run(d.diagnose_pyprover_failure(NotImplementedError("unsupported BinOp")))
        assert "supported subset" in " ".join(result["suggestions"])
        assert result["suggestions"] != ["Simplify code"]

    def test_different_exceptions_get_different_suggestions(self):
        d = ToolDiagnostician()

        async def run():
            r1 = await d.diagnose_pyprover_failure(NotImplementedError("x"))
            r2 = await d.diagnose_pyprover_failure(TimeoutError("solver timeout"))
            r3 = await d.diagnose_pyprover_failure(SyntaxError("bad contract"))
            return r1, r2, r3

        r1, r2, r3 = asyncio.run(run())
        assert r1["suggestions"] != r2["suggestions"] != r3["suggestions"]

    def test_unrecognized_exception_falls_back_honestly(self):
        d = ToolDiagnostician()
        result = asyncio.run(d.diagnose_pyprover_failure(ValueError("some other issue")))
        assert "ValueError" in result["cause"]


class TestHealthCheckerRealProbes:
    def test_reports_all_components(self):
        h = HealthChecker()
        health = asyncio.run(h.check_all_tools())
        for component in ("pyprover", "python_debug", "test_generator",
                           "code_orchestrator", "troubleshooting", "master_debugger"):
            assert component in health
            assert health[component]["status"] in ("healthy", "degraded")

    def test_status_depends_on_real_tool_availability(self):
        """Regression check for the hardcoded-'healthy' stub: pyprover's
        status must actually depend on whether z3 is importable, not be
        a constant."""
        h = HealthChecker()
        health = asyncio.run(h.check_all_tools())
        import importlib.util
        z3_installed = importlib.util.find_spec("z3") is not None
        expected = "healthy" if z3_installed else "degraded"
        assert health["pyprover"]["status"] == expected

    def test_details_include_real_probe_results_not_placeholders(self):
        h = HealthChecker()
        health = asyncio.run(h.check_all_tools())
        assert "z3-solver" in health["pyprover"]["details"]
        assert isinstance(health["pyprover"]["details"]["z3-solver"], str)
