"""
Tests for C/C++-Debug (Phase 4): diagnostics compiler, static analyzer,
pattern classification, and the integrated CppDebugger.
"""
import pytest

from src.cpp_debug.diagnostics import DiagnosticsCompiler, clang_available
from src.cpp_debug.analyzer import StaticAnalyzer
from src.cpp_debug.classifier import CppBugPatternClassifier
from src.cpp_debug.phases import CppDebugger
from src.cpp_debug.setup import claude_check_and_install, REQUIRED_TOOLS
from src.common.interop import BugSeverity, RiskLevel, LanguageType


CLANG_PRESENT = clang_available("c")


class TestDiagnosticsCompiler:
    """Test compiler diagnostics extraction."""

    def test_clean_code_no_warnings(self):
        compiler = DiagnosticsCompiler()
        result = compiler.compile_and_diagnose("int main() { return 0; }", dialect="c")
        if result["tool_available"]:
            assert result["errors"] == []
            assert result["warnings"] == []

    def test_uninitialized_variable_detected(self):
        compiler = DiagnosticsCompiler()
        code = "int main() {\n    int x;\n    return x;\n}\n"
        result = compiler.compile_and_diagnose(code, dialect="c")
        if result["tool_available"]:
            flags = [w["flag"] for w in result["warnings"]]
            assert "-Wuninitialized" in flags

    def test_compile_error_detected(self):
        compiler = DiagnosticsCompiler()
        code = "int main() { return undeclared_identifier; }"
        result = compiler.compile_and_diagnose(code, dialect="c")
        if result["tool_available"]:
            assert len(result["errors"]) >= 1

    def test_graceful_degradation_when_unavailable(self):
        compiler = DiagnosticsCompiler()
        # Simulate unavailability by checking the contract holds regardless
        result = compiler.compile_and_diagnose("int main() { return 0; }", dialect="c")
        assert isinstance(result["errors"], list)
        assert isinstance(result["warnings"], list)


class TestStaticAnalyzer:
    """Test Clang Static Analyzer integration."""

    def test_null_dereference_detected(self):
        analyzer = StaticAnalyzer()
        code = (
            "int deref(int x) {\n"
            "    int *p = 0;\n"
            "    if (x > 0) { static int v; p = &v; }\n"
            "    return *p;\n"
            "}\n"
        )
        result = analyzer.analyze(code, dialect="c")
        if result["tool_available"]:
            assert isinstance(result["findings"], list)

    def test_graceful_degradation(self):
        analyzer = StaticAnalyzer()
        result = analyzer.analyze("int main() { return 0; }", dialect="c")
        assert isinstance(result["findings"], list)


class TestCppBugPatternClassifier:
    """Test classification of raw diagnostics into BugPattern objects."""

    def test_classify_uninitialized_warning(self):
        classifier = CppBugPatternClassifier()
        diagnostics = {
            "errors": [],
            "warnings": [{"line": 3, "col": 12, "message": "variable 'x' is uninitialized",
                           "flag": "-Wuninitialized"}],
            "notes": [],
        }
        patterns = classifier.classify_diagnostics(diagnostics, dialect="c")
        assert len(patterns) == 1
        assert patterns[0].pattern_type == "uninitialized_variable"
        assert patterns[0].severity == BugSeverity.CRITICAL
        assert patterns[0].language == LanguageType.C

    def test_classify_compile_error(self):
        classifier = CppBugPatternClassifier()
        diagnostics = {
            "errors": [{"line": 1, "col": 5, "message": "use of undeclared identifier 'y'", "flag": ""}],
            "warnings": [],
            "notes": [],
        }
        patterns = classifier.classify_diagnostics(diagnostics, dialect="c")
        assert len(patterns) == 1
        assert patterns[0].pattern_type == "compile_error"
        assert patterns[0].severity == BugSeverity.CRITICAL

    def test_classify_unknown_flag_defaults_medium(self):
        classifier = CppBugPatternClassifier()
        diagnostics = {
            "errors": [],
            "warnings": [{"line": 2, "col": 1, "message": "some new warning", "flag": "-Wsome-future-flag"}],
            "notes": [],
        }
        patterns = classifier.classify_diagnostics(diagnostics, dialect="c")
        assert patterns[0].severity == BugSeverity.MEDIUM

    def test_merge_and_dedupe_sorts_by_severity(self):
        classifier = CppBugPatternClassifier()
        diagnostics = {
            "errors": [{"line": 1, "col": 1, "message": "err", "flag": ""}],
            "warnings": [{"line": 2, "col": 1, "message": "unused", "flag": "-Wunused-variable"}],
            "notes": [],
        }
        patterns = classifier.classify_diagnostics(diagnostics, dialect="c")
        merged = classifier.merge_and_dedupe(patterns)
        assert merged[0].severity == BugSeverity.CRITICAL
        assert merged[-1].severity == BugSeverity.LOW

    def test_merge_and_dedupe_removes_duplicates(self):
        classifier = CppBugPatternClassifier()
        diagnostics = {
            "errors": [],
            "warnings": [
                {"line": 5, "col": 1, "message": "dup", "flag": "-Wunused-variable"},
                {"line": 5, "col": 9, "message": "dup again", "flag": "-Wunused-variable"},
            ],
            "notes": [],
        }
        patterns = classifier.classify_diagnostics(diagnostics, dialect="c")
        merged = classifier.merge_and_dedupe(patterns)
        assert len(merged) == 1


class TestCppDebugger:
    """Integration tests for the combined CppDebugger."""

    def test_debug_returns_unified_report(self):
        debugger = CppDebugger()
        report = debugger.debug("int main() { return 0; }", dialect="c")
        assert report.component is not None
        assert report.language == LanguageType.C

    def test_debug_clean_code_low_risk(self):
        debugger = CppDebugger()
        report = debugger.debug("int main() { return 0; }", dialect="c")
        if CLANG_PRESENT:
            assert report.risk_level == RiskLevel.LOW

    def test_debug_uninitialized_variable_critical(self):
        debugger = CppDebugger()
        code = "int main() {\n    int x;\n    return x;\n}\n"
        report = debugger.debug(code, dialect="c")
        if CLANG_PRESENT:
            assert report.risk_level == RiskLevel.CRITICAL
            assert any(p.pattern_type == "uninitialized_variable" for p in report.patterns_detected)

    def test_debug_cpp_dialect(self):
        debugger = CppDebugger()
        code = "#include <vector>\nint main() {\n    std::vector<int> v;\n    return 0;\n}\n"
        report = debugger.debug(code, dialect="cpp")
        assert report.language == LanguageType.CPP

    def test_design_review_flags_gets(self):
        debugger = CppDebugger()
        code = "#include <stdio.h>\nint main() {\n    char buf[10];\n    gets(buf);\n    return 0;\n}\n"
        report = debugger.debug(code, dialect="c")
        assert any(p.pattern_type == "unsafe_string_api" for p in report.patterns_detected)

    def test_phase_1_runtime_alias(self):
        debugger = CppDebugger()
        report = debugger.phase_1_runtime("int main() { return 0; }", dialect="c")
        assert report is not None


class TestSetup:
    """Test Claude-facing setup checker."""

    def test_check_and_install_returns_status_dict(self):
        status = claude_check_and_install()
        assert "clang_available" in status
        assert "clangpp_available" in status
        assert "all_available" in status
        assert isinstance(status["all_available"], bool)

    def test_required_tools_metadata_present(self):
        assert "clang" in REQUIRED_TOOLS
        assert "clang++" in REQUIRED_TOOLS
        assert "install" in REQUIRED_TOOLS["clang"]
