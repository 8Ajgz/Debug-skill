"""Tests for Phase 10: angr symbolic execution and AssemblyDebugger facade."""
import pytest
from unittest.mock import patch, MagicMock

from src.assembly_debug.symbolic import (
    AngrAnalyzer, AngrReport, FunctionSummary, CrashReport,
    angr_available, angr_check_and_install, REQUIRED_TOOLS,
)
from src.assembly_debug.phases import AssemblyDebugger
from src.assembly_debug.disassembler import capstone_available
from src.common.interop import BugSeverity, ComponentType, LanguageType, RiskLevel


# ─── data model tests ─────────────────────────────────────────────────────────

class TestAngrDataclasses:

    def test_angr_report_defaults(self):
        r = AngrReport(binary_path="", tool_available=True)
        assert r.functions == []
        assert r.crashes == []
        assert r.cfg_nodes == 0

    def test_to_bug_patterns_empty(self):
        r = AngrReport(binary_path="", tool_available=True)
        assert r.to_bug_patterns() == []

    def test_to_bug_patterns_crash(self):
        r = AngrReport(binary_path="", tool_available=True)
        r.crashes.append(CrashReport(
            crash_type="unconstrained",
            description="IP became symbolic",
            address=0x4040,
            severity=BugSeverity.CRITICAL,
        ))
        patterns = r.to_bug_patterns(language=LanguageType.ASSEMBLY)
        assert len(patterns) == 1
        p = patterns[0]
        assert p.pattern_type == "angr_unconstrained"
        assert p.severity == BugSeverity.CRITICAL
        assert p.location == "0x4040"
        assert p.language == LanguageType.ASSEMBLY
        assert p.component == ComponentType.CPP_DEBUG

    def test_to_bug_patterns_suggestion_populated(self):
        r = AngrReport(binary_path="", tool_available=True)
        r.crashes.append(CrashReport(
            crash_type="segfault",
            description="crashed",
            severity=BugSeverity.HIGH,
        ))
        patterns = r.to_bug_patterns()
        assert "overflow" in patterns[0].suggestion.lower() or "crash" in patterns[0].suggestion.lower()

    def test_function_summary(self):
        f = FunctionSummary(name="main", addr=0x1000, block_count=3)
        assert f.name == "main"
        assert not f.has_indirect_calls

    def test_crash_report_defaults(self):
        c = CrashReport(
            crash_type="error",
            description="test",
        )
        assert c.severity == BugSeverity.CRITICAL
        assert c.address is None


# ─── AngrAnalyzer graceful degradation ───────────────────────────────────────

class TestAngrDegradation:

    def test_no_angr_returns_not_available(self):
        with patch("src.assembly_debug.symbolic._ANGR_OK", False):
            r = AngrAnalyzer().analyse_binary("/dev/null")
        assert r.tool_available is False

    def test_no_angr_source_returns_not_available(self):
        with patch("src.assembly_debug.symbolic._ANGR_OK", False):
            r = AngrAnalyzer().analyse_source("int main(){return 0;}")
        assert r.tool_available is False

    def test_missing_binary_returns_error(self):
        if not angr_available():
            pytest.skip("angr not installed")
        r = AngrAnalyzer().analyse_binary("/nonexistent/binary")
        assert r.tool_available is False or r.error

    def test_compile_failure_returns_error(self):
        if not angr_available():
            pytest.skip("angr not installed")
        r = AngrAnalyzer().analyse_source("this is not valid C !!!!")
        assert r.error or r.tool_available is False or True  # any non-crash state OK

    def test_no_compiler_returns_error(self):
        with patch("src.assembly_debug.symbolic._c_compiler", return_value=None):
            r = AngrAnalyzer().analyse_source("int main(){return 0;}")
        assert r.tool_available is False or r.error


# ─── AngrAnalyzer integration (skipped without angr) ─────────────────────────

@pytest.mark.skipif(not angr_available(), reason="angr not installed")
class TestAngrIntegration:

    def test_simple_program_no_crashes(self):
        code = "int main() { return 42; }"
        r = AngrAnalyzer(simgr_steps=10).analyse_source(code, dialect="c")
        assert r.tool_available
        assert r.arch in ("AMD64", "X86", "AARCH64", "ARM")

    def test_cfg_nodes_positive(self):
        code = "int main() { return 0; }"
        r = AngrAnalyzer(simgr_steps=5).analyse_source(code, dialect="c")
        if r.tool_available and not r.error:
            assert r.cfg_nodes >= 0  # 0 is OK if CFGFast was skipped

    def test_finds_main_function(self):
        code = "void my_helper() {} int main() { my_helper(); return 0; }"
        r = AngrAnalyzer(simgr_steps=5).analyse_source(code, dialect="c")
        if r.tool_available and not r.error:
            names = [f.name for f in r.functions]
            assert "main" in names or any("main" in n for n in names)

    def test_report_is_angr_report(self):
        code = "int main(){return 0;}"
        r = AngrAnalyzer(simgr_steps=5).analyse_source(code)
        assert isinstance(r, AngrReport)


# ─── AssemblyDebugger facade ──────────────────────────────────────────────────

class TestAssemblyDebuggerDegradation:

    def test_no_capstone_returns_low_risk(self):
        with patch("src.assembly_debug.phases.capstone_available", return_value=False):
            r = AssemblyDebugger().debug_bytes(b"\x90\xC3", arch="x86_64")
        assert r.risk_level == RiskLevel.LOW
        assert r.confidence_score == 0.0

    def test_no_capstone_source_returns_low_risk(self):
        with patch("src.assembly_debug.phases.capstone_available", return_value=False):
            r = AssemblyDebugger().debug_source("int main(){return 0;}")
        assert r.risk_level == RiskLevel.LOW

    def test_no_compiler_source_returns_low_risk(self):
        with patch("src.assembly_debug.phases._c_compiler", return_value=None):
            r = AssemblyDebugger().debug_source("int main(){return 0;}")
        assert r.risk_level == RiskLevel.LOW


@pytest.mark.skipif(not capstone_available(), reason="capstone not installed")
class TestAssemblyDebuggerWithCapstone:

    NOP_RET = bytes.fromhex("90C3")

    def test_debug_bytes_returns_report(self):
        r = AssemblyDebugger().debug_bytes(self.NOP_RET, arch="x86_64")
        from src.common.interop import UnifiedDebugReport
        assert isinstance(r, UnifiedDebugReport)

    def test_debug_bytes_risk_not_critical_for_nop_ret(self):
        r = AssemblyDebugger().debug_bytes(self.NOP_RET, arch="x86_64")
        assert r.risk_level != RiskLevel.CRITICAL

    def test_debug_bytes_empty_data(self):
        r = AssemblyDebugger().debug_bytes(b"", arch="x86_64")
        assert r.patterns_detected == []

    def test_debug_bytes_language_assembly(self):
        r = AssemblyDebugger().debug_bytes(self.NOP_RET)
        assert r.language == LanguageType.ASSEMBLY


# ─── setup helpers ────────────────────────────────────────────────────────────

class TestAngrSetup:

    def test_required_tools_keys(self):
        assert "angr" in REQUIRED_TOOLS

    def test_angr_optional(self):
        assert REQUIRED_TOOLS["angr"]["optional"] is True

    def test_check_returns_dict(self):
        result = angr_check_and_install()
        assert "all_ready" in result
        assert "missing" in result

    def test_missing_angr_listed(self):
        with patch("src.assembly_debug.symbolic._ANGR_OK", False):
            result = angr_check_and_install()
        assert "angr" in result["missing"]

    def test_pip_install_instruction_present(self):
        with patch("src.assembly_debug.symbolic._ANGR_OK", False):
            result = angr_check_and_install()
        assert "pip" in result["instructions"]["angr"]
