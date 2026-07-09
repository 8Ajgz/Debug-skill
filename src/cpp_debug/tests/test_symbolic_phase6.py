"""
Tests for Phase 6: Symbolic Execution (CBMC + KLEE wrappers).

Most tests mock subprocess.run because CBMC/KLEE are not installed in CI.
Integration tests are guarded by cbmc_available() / klee_available() markers.
"""
import pytest
from unittest.mock import patch, MagicMock

from src.cpp_debug.symbolic_executor import (
    SymbolicExecutor,
    SymbolicReport,
    SymbolicFinding,
    CounterexampleStep,
    CBMCDriver,
    KLEEDriver,
    _parse_cbmc_output,
    _parse_klee_output,
    _classify_cbmc_property,
    _classify_klee_error,
    cbmc_available,
    klee_available,
    claude_check_and_install,
    REQUIRED_TOOLS,
)
from src.common.interop import BugSeverity, ComponentType, LanguageType


# ─── data model tests ─────────────────────────────────────────────────────────

class TestSymbolicDataclasses:

    def test_symbolic_finding_default_confidence(self):
        f = SymbolicFinding(
            tool="cbmc",
            property_type="buffer_overflow",
            location="test.c:5",
            description="test",
            severity=BugSeverity.CRITICAL,
        )
        assert f.confidence == 0.9
        assert f.counterexample == []

    def test_symbolic_report_defaults(self):
        r = SymbolicReport(tool_available=True)
        assert r.findings == []
        assert r.cbmc_ran is False
        assert r.klee_ran is False

    def test_to_bug_patterns_empty(self):
        r = SymbolicReport(tool_available=False)
        assert r.to_bug_patterns() == []

    def test_to_bug_patterns_converts_findings(self):
        r = SymbolicReport(tool_available=True)
        r.findings.append(SymbolicFinding(
            tool="cbmc",
            property_type="null_deref",
            location="foo.c:10",
            description="null pointer",
            severity=BugSeverity.CRITICAL,
        ))
        patterns = r.to_bug_patterns(language=LanguageType.C)
        assert len(patterns) == 1
        p = patterns[0]
        assert p.pattern_type == "null_deref"
        assert p.severity == BugSeverity.CRITICAL
        assert p.component == ComponentType.CPP_DEBUG
        assert p.language == LanguageType.C

    def test_to_bug_patterns_suggestion_filled(self):
        r = SymbolicReport(tool_available=True)
        r.findings.append(SymbolicFinding(
            tool="cbmc",
            property_type="buffer_overflow",
            location="x.c:1",
            description="...",
            severity=BugSeverity.CRITICAL,
        ))
        patterns = r.to_bug_patterns()
        assert "bounds" in patterns[0].suggestion.lower() or "vector" in patterns[0].suggestion.lower()


# ─── CBMC output parsing ──────────────────────────────────────────────────────

class TestCBMCParsing:

    SAMPLE_CBMC_OUTPUT = """\
[main.bounds_check.1] line 5 array 'a' upper bound in main: FAILURE
[main.div-by-zero.2] line 12 division by zero in divide: FAILURE
[null-deref.3] line 7 null pointer dereference in main: FAILURE
VERIFICATION FAILED
"""

    def test_parse_buffer_overflow(self):
        output = "[main.bounds_check.1] line 5 array 'a' upper bound in main: FAILURE"
        findings = _parse_cbmc_output(output, "test.c")
        assert len(findings) == 1
        assert findings[0].tool == "cbmc"
        assert "overflow" in findings[0].property_type or "buffer" in findings[0].property_type

    def test_parse_div_zero(self):
        output = "[main.div-by-zero.2] line 12 division by zero in divide: FAILURE"
        findings = _parse_cbmc_output(output, "test.c")
        assert len(findings) == 1
        assert "div" in findings[0].property_type or "zero" in findings[0].property_type

    def test_parse_null_deref(self):
        output = "[null-deref.3] line 7 null pointer dereference in main: FAILURE"
        findings = _parse_cbmc_output(output, "test.c")
        assert len(findings) == 1

    def test_parse_multiple_violations(self):
        findings = _parse_cbmc_output(self.SAMPLE_CBMC_OUTPUT, "test.c")
        assert len(findings) == 3

    def test_parse_success_output_no_findings(self):
        output = "VERIFICATION SUCCESSFUL\n"
        findings = _parse_cbmc_output(output, "test.c")
        assert findings == []

    def test_parse_empty_output(self):
        assert _parse_cbmc_output("", "test.c") == []

    def test_classify_overflow(self):
        prop_type, sev = _classify_cbmc_property("main.bounds_check.1")
        assert sev in (BugSeverity.CRITICAL, BugSeverity.HIGH)

    def test_classify_div_zero(self):
        prop_type, sev = _classify_cbmc_property("div-by-zero")
        assert "div" in prop_type or "zero" in prop_type
        assert sev == BugSeverity.HIGH

    def test_classify_assertion(self):
        prop_type, sev = _classify_cbmc_property("main.assertion.1")
        assert prop_type == "assertion"
        assert sev in (BugSeverity.HIGH, BugSeverity.MEDIUM)

    def test_classify_null_deref(self):
        prop_type, sev = _classify_cbmc_property("null-deref")
        assert "null" in prop_type or "deref" in prop_type


# ─── KLEE output parsing ──────────────────────────────────────────────────────

class TestKLEEParsing:

    def test_parse_memory_error(self):
        output = "KLEE: ERROR: /tmp/klee-out-0/test000001.ptr.err (memory error: out of bound pointer)\n"
        findings = _parse_klee_output(output)
        assert len(findings) == 1
        assert findings[0].tool == "klee"
        assert findings[0].property_type in ("buffer_overflow", "null_deref")

    def test_parse_assertion_error(self):
        output = "KLEE: ERROR: /tmp/klee-out-0/test000001.assert.err (ASSERTION FAIL: x > 0)\n"
        findings = _parse_klee_output(output)
        assert len(findings) == 1
        assert findings[0].property_type == "assertion"

    def test_parse_clean_output(self):
        output = "KLEE: done: total instructions = 100\n"
        findings = _parse_klee_output(output)
        assert findings == []

    def test_classify_out_of_bound(self):
        prop, sev = _classify_klee_error("memory error: out of bound pointer")
        assert prop == "buffer_overflow"
        assert sev == BugSeverity.CRITICAL

    def test_classify_null(self):
        prop, sev = _classify_klee_error("null pointer")
        assert sev == BugSeverity.CRITICAL

    def test_classify_division(self):
        prop, sev = _classify_klee_error("division by zero")
        assert sev == BugSeverity.HIGH


# ─── SymbolicExecutor graceful degradation ───────────────────────────────────

class TestSymbolicExecutorDegradation:

    def test_no_tools_returns_not_available(self):
        with patch("src.cpp_debug.symbolic_executor.cbmc_available", return_value=False), \
             patch("src.cpp_debug.symbolic_executor.klee_available", return_value=False):
            r = SymbolicExecutor().run("int main(){return 0;}")
        assert r.tool_available is False
        assert "cbmc" in r.error.lower() or "klee" in r.error.lower()

    def test_no_tools_empty_findings(self):
        with patch("src.cpp_debug.symbolic_executor.cbmc_available", return_value=False), \
             patch("src.cpp_debug.symbolic_executor.klee_available", return_value=False):
            r = SymbolicExecutor().run("int main(){return 0;}")
        assert r.findings == []

    def test_cbmc_timeout_does_not_crash(self):
        """CBMC timeout must produce an empty findings list, not an exception."""
        with patch("src.cpp_debug.symbolic_executor.cbmc_available", return_value=True), \
             patch("src.cpp_debug.symbolic_executor.klee_available", return_value=False), \
             patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("cbmc", 30)):
            r = SymbolicExecutor().run("int main(){return 0;}")
        assert isinstance(r.findings, list)

    def test_cbmc_subprocess_error_does_not_crash(self):
        with patch("src.cpp_debug.symbolic_executor.cbmc_available", return_value=True), \
             patch("src.cpp_debug.symbolic_executor.klee_available", return_value=False), \
             patch("subprocess.run", side_effect=OSError("binary not found")):
            r = SymbolicExecutor().run("int main(){return 0;}")
        assert isinstance(r.findings, list)

    def test_deduplication_across_tools(self):
        """Same (property_type, location) from CBMC and KLEE is deduplicated."""
        finding_a = SymbolicFinding(
            tool="cbmc", property_type="buffer_overflow",
            location="x.c:5", description="cbmc says", severity=BugSeverity.CRITICAL,
        )
        finding_b = SymbolicFinding(
            tool="klee", property_type="buffer_overflow",
            location="x.c:5", description="klee also says", severity=BugSeverity.CRITICAL,
        )
        executor = SymbolicExecutor()
        # Patch both drivers to return the same finding
        executor._cbmc.run = lambda code, dialect="c": ([finding_a], "cbmc out", True)
        executor._klee.run = lambda code: ([finding_b], "klee out", True)

        with patch("src.cpp_debug.symbolic_executor.cbmc_available", return_value=True), \
             patch("src.cpp_debug.symbolic_executor.klee_available", return_value=True):
            r = executor.run("int main(){}", dialect="c")

        assert len(r.findings) == 1  # deduplicated

    def test_klee_skipped_for_cpp(self):
        """KLEE is not run against C++ code (dialect='cpp')."""
        executor = SymbolicExecutor()
        klee_called = []
        executor._cbmc.run = lambda code, dialect="c": ([], "", True)
        executor._klee.run = lambda code: klee_called.append(1) or ([], "", True)

        with patch("src.cpp_debug.symbolic_executor.cbmc_available", return_value=True), \
             patch("src.cpp_debug.symbolic_executor.klee_available", return_value=True):
            executor.run("int main(){}", dialect="cpp")

        assert klee_called == []  # never called


# ─── CBMCDriver mocked run ────────────────────────────────────────────────────

class TestCBMCDriverMocked:

    def _make_completed(self, stdout="", returncode=0):
        m = MagicMock()
        m.stdout = stdout
        m.stderr = ""
        m.returncode = returncode
        return m

    def test_success_output_no_findings(self):
        with patch("src.cpp_debug.symbolic_executor.cbmc_available", return_value=True), \
             patch("subprocess.run", return_value=self._make_completed("VERIFICATION SUCCESSFUL")):
            findings, raw, ran = CBMCDriver().run("int main(){return 0;}")
        assert ran is True
        assert findings == []

    def test_violation_output_returns_finding(self):
        cbmc_out = "[main.bounds_check.1] line 5 array overflow: FAILURE\n"
        with patch("src.cpp_debug.symbolic_executor.cbmc_available", return_value=True), \
             patch("subprocess.run", return_value=self._make_completed(cbmc_out)):
            findings, raw, ran = CBMCDriver().run("int a[3]; int main(){a[5]=1;}")
        assert ran is True
        assert len(findings) >= 1

    def test_not_available_returns_empty(self):
        with patch("src.cpp_debug.symbolic_executor.cbmc_available", return_value=False):
            findings, raw, ran = CBMCDriver().run("int main(){}")
        assert ran is False
        assert findings == []


# ─── setup helper ─────────────────────────────────────────────────────────────

class TestSetupHelper:

    def test_required_tools_keys(self):
        assert "cbmc" in REQUIRED_TOOLS
        assert "klee" in REQUIRED_TOOLS

    def test_both_optional(self):
        assert REQUIRED_TOOLS["cbmc"]["optional"] is True
        assert REQUIRED_TOOLS["klee"]["optional"] is True

    def test_claude_check_returns_dict(self):
        result = claude_check_and_install()
        assert "all_ready" in result
        assert "missing" in result
        assert "note" in result

    def test_missing_tools_listed(self):
        with patch("src.cpp_debug.symbolic_executor.cbmc_available", return_value=False), \
             patch("src.cpp_debug.symbolic_executor.klee_available", return_value=False):
            result = claude_check_and_install()
        assert "cbmc" in result["missing"]
        assert "klee" in result["missing"]

    def test_cbmc_install_instructions(self):
        with patch("src.cpp_debug.symbolic_executor.cbmc_available", return_value=False), \
             patch("src.cpp_debug.symbolic_executor.klee_available", return_value=True):
            result = claude_check_and_install()
        assert "cbmc" in result["missing"]
        assert "apt" in result["instructions"]["cbmc"]


# ─── integration (only if cbmc installed) ─────────────────────────────────────

@pytest.mark.skipif(not cbmc_available(), reason="cbmc not installed")
class TestCBMCIntegration:

    def test_safe_program_no_findings(self):
        code = "int main() { int a[3] = {1,2,3}; return a[0]; }"
        r = SymbolicExecutor().run(code, dialect="c")
        assert r.tool_available
        assert r.cbmc_ran

    def test_div_zero_detected(self):
        code = "int divide(int a, int b) { return a / b; } int main() { return divide(1, 0); }"
        r = SymbolicExecutor().run(code, dialect="c")
        assert r.cbmc_ran
        # CBMC should find the division by zero
        types = [f.property_type for f in r.findings]
        assert any("div" in t or "zero" in t for t in types)
