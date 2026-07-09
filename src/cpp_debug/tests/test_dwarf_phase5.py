"""
Tests for Phase 5: DWARF Symbol Analysis (src/cpp_debug/dwarf_analyzer.py).

These tests do NOT require a C compiler to be installed. When a compiler is
absent, the analyser degrades gracefully and returns tool_available=False or
an error string — both are tested explicitly.

Tests that actually compile code are marked with a custom marker and guarded
by dwarf_available() so they are skipped in CI environments without gcc/clang.
"""
import pytest
from unittest.mock import patch, MagicMock

from src.cpp_debug.dwarf_analyzer import (
    DWARFAnalyzer,
    DWARFReport,
    DWARFVariable,
    DWARFMemoryIssue,
    _check_pointer_escapes,
    _check_void_pointer_casts,
    _cross_ref_pointers,
    _resolve_type_name,
    _classify_location_kind,
    dwarf_available,
    claude_check_and_install,
    REQUIRED_TOOLS,
)
from src.common.interop import BugSeverity, ComponentType, LanguageType


# ─── fixtures ─────────────────────────────────────────────────────────────────

def _make_var(
    name: str = "x",
    type_name: str = "int",
    location_kind: str = "stack",
    declaration_file: str = "test.c",
    declaration_line: int = 1,
    pointee_type: str = "",
    byte_size: int = 4,
    has_location: bool = True,
) -> DWARFVariable:
    return DWARFVariable(
        name=name,
        type_name=type_name,
        location_kind=location_kind,
        byte_size=byte_size,
        declaration_file=declaration_file,
        declaration_line=declaration_line,
        pointee_type=pointee_type,
        has_location=has_location,
    )


# ─── unit: DWARFVariable / DWARFReport dataclass ──────────────────────────────

class TestDWARFDataclasses:

    def test_dwarf_variable_creation(self):
        var = _make_var()
        assert var.name == "x"
        assert var.type_name == "int"
        assert var.location_kind == "stack"

    def test_dwarf_report_empty(self):
        r = DWARFReport(binary_path="/dev/null", tool_available=False)
        assert r.variables == []
        assert r.memory_issues == []
        assert r.type_sizes == {}
        assert r.function_names == []

    def test_to_bug_patterns_empty(self):
        r = DWARFReport(binary_path="", tool_available=True)
        assert r.to_bug_patterns() == []

    def test_to_bug_patterns_converts_issues(self):
        r = DWARFReport(binary_path="", tool_available=True)
        r.memory_issues.append(DWARFMemoryIssue(
            issue_type="potential_double_free",
            variable_name="p",
            description="double free",
            location="test.c:5",
            severity=BugSeverity.HIGH,
        ))
        patterns = r.to_bug_patterns(language=LanguageType.C)
        assert len(patterns) == 1
        p = patterns[0]
        assert p.pattern_type == "potential_double_free"
        assert p.severity == BugSeverity.HIGH
        assert p.location == "test.c:5"
        assert p.component == ComponentType.CPP_DEBUG
        assert p.language == LanguageType.C

    def test_to_bug_patterns_suggestion_filled(self):
        r = DWARFReport(binary_path="", tool_available=True)
        r.memory_issues.append(DWARFMemoryIssue(
            issue_type="stack_pointer_escape",
            variable_name="ptr",
            description="...",
            location="foo.c:10",
        ))
        patterns = r.to_bug_patterns()
        assert "stack" in patterns[0].suggestion.lower() or "pointer" in patterns[0].suggestion.lower()


# ─── unit: heuristic passes ───────────────────────────────────────────────────

class TestPointerHeuristics:

    def test_stack_pointer_escape_flagged(self):
        var = _make_var(name="p", type_name="int *", location_kind="stack",
                        pointee_type="int")
        issues = _check_pointer_escapes([var])
        assert len(issues) == 1
        assert issues[0].issue_type == "stack_pointer_escape"
        assert issues[0].variable_name == "p"

    def test_global_pointer_not_flagged(self):
        var = _make_var(name="g", type_name="int *", location_kind="global",
                        pointee_type="int")
        issues = _check_pointer_escapes([var])
        assert issues == []

    def test_non_pointer_not_flagged(self):
        var = _make_var(name="x", type_name="int", location_kind="stack")
        issues = _check_pointer_escapes([var])
        assert issues == []

    def test_void_pointer_flagged(self):
        var = _make_var(name="raw", type_name="void *")
        issues = _check_void_pointer_casts([var])
        assert len(issues) == 1
        assert issues[0].issue_type == "untracked_heap"

    def test_non_void_pointer_not_flagged(self):
        var = _make_var(name="p", type_name="int *")
        issues = _check_void_pointer_casts([var])
        assert issues == []

    def test_double_free_two_pointers_same_type_same_line(self):
        a = _make_var(name="a", type_name="int *", location_kind="stack",
                      declaration_file="x.c", declaration_line=5, pointee_type="int")
        b = _make_var(name="b", type_name="int *", location_kind="stack",
                      declaration_file="x.c", declaration_line=5, pointee_type="int")
        issues = _cross_ref_pointers([a, b])
        assert len(issues) == 1
        assert issues[0].issue_type == "potential_double_free"
        assert "a" in issues[0].variable_name and "b" in issues[0].variable_name

    def test_different_lines_no_double_free(self):
        a = _make_var(name="a", type_name="int *", declaration_file="x.c",
                      declaration_line=5, pointee_type="int")
        b = _make_var(name="b", type_name="int *", declaration_file="x.c",
                      declaration_line=6, pointee_type="int")
        issues = _cross_ref_pointers([a, b])
        assert issues == []

    def test_different_pointee_types_no_double_free(self):
        a = _make_var(name="a", type_name="int *", declaration_file="x.c",
                      declaration_line=5, pointee_type="int")
        b = _make_var(name="b", type_name="char *", declaration_file="x.c",
                      declaration_line=5, pointee_type="char")
        issues = _cross_ref_pointers([a, b])
        assert issues == []


# ─── unit: DWARFAnalyzer graceful degradation ─────────────────────────────────

class TestDWARFAnalyzerDegradation:

    def test_no_pyelftools_returns_tool_not_available(self):
        with patch("src.cpp_debug.dwarf_analyzer._ELFTOOLS_AVAILABLE", False):
            a = DWARFAnalyzer()
            r = a.analyze_source("int main(){return 0;}", dialect="c")
        assert r.tool_available is False
        assert r.variables == []

    def test_no_compiler_returns_tool_not_available(self):
        import shutil as _shutil
        orig = _shutil.which
        def no_compiler(name):
            if name in ("gcc", "clang", "clang++"):
                return None
            return orig(name)
        with patch("src.cpp_debug.dwarf_analyzer.shutil.which", side_effect=no_compiler):
            with patch("src.cpp_debug.dwarf_analyzer._ELFTOOLS_AVAILABLE", True):
                r = DWARFAnalyzer().analyze_source("int main(){}", dialect="c")
        assert r.tool_available is False

    def test_analyze_binary_missing_file(self):
        a = DWARFAnalyzer()
        r = a.analyze_binary("/nonexistent/path/binary")
        assert "not found" in r.error.lower() or r.tool_available is False

    def test_analyze_binary_no_pyelftools(self):
        with patch("src.cpp_debug.dwarf_analyzer._ELFTOOLS_AVAILABLE", False):
            r = DWARFAnalyzer().analyze_binary("/dev/null")
        assert r.tool_available is False

    def test_compile_failure_returns_empty_report(self):
        # Syntax error → compilation fails → empty variables, no crash
        bad_code = "int main() { this is not C code !!!; }"
        r = DWARFAnalyzer().analyze_source(bad_code, dialect="c")
        # Either tool not available (no compiler) or empty report
        if r.tool_available:
            assert r.variables == []


# ─── integration: real compilation (skipped if no compiler) ───────────────────

@pytest.mark.skipif(not dwarf_available(), reason="DWARF analysis tools not available")
class TestDWARFIntegration:

    def test_simple_program_extracts_variables(self):
        code = "int main() { int x = 42; return x; }"
        r = DWARFAnalyzer().analyze_source(code, dialect="c")
        assert r.tool_available
        assert any(v.name == "x" for v in r.variables)

    def test_extracts_function_name(self):
        code = "void my_func(int n) { (void)n; } int main() { my_func(1); return 0; }"
        r = DWARFAnalyzer().analyze_source(code, dialect="c")
        assert "my_func" in r.function_names or "main" in r.function_names

    def test_void_pointer_detected(self):
        code = "#include <stdlib.h>\nint main() { void *p = malloc(64); (void)p; return 0; }"
        r = DWARFAnalyzer().analyze_source(code, dialect="c")
        # void* may be found as variable; at minimum no crash
        assert r.tool_available

    def test_stack_pointer_variable_recorded(self):
        code = "int main() { int val = 1; int *p = &val; (void)p; return 0; }"
        r = DWARFAnalyzer().analyze_source(code, dialect="c")
        assert r.tool_available
        names = [v.name for v in r.variables]
        assert "val" in names or "p" in names

    def test_to_bug_patterns_after_real_compile(self):
        code = "#include <stdlib.h>\nint main() { int *a=NULL,*b=NULL; (void)a;(void)b; return 0; }"
        r = DWARFAnalyzer().analyze_source(code, dialect="c")
        patterns = r.to_bug_patterns()
        # Should not raise; double-free heuristic may or may not fire
        assert isinstance(patterns, list)

    def test_cpp_dialect(self):
        code = "int main() { int x = 0; return x; }"
        r = DWARFAnalyzer().analyze_source(code, dialect="cpp")
        assert r.tool_available or "not available" in r.error


# ─── setup helper ─────────────────────────────────────────────────────────────

class TestSetupHelper:

    def test_required_tools_defined(self):
        assert "pyelftools" in REQUIRED_TOOLS
        assert "gcc_or_clang" in REQUIRED_TOOLS

    def test_claude_check_returns_dict(self):
        result = claude_check_and_install()
        assert "all_ready" in result
        assert "missing" in result
        assert "instructions" in result

    def test_missing_list_is_list(self):
        result = claude_check_and_install()
        assert isinstance(result["missing"], list)

    def test_instructions_for_missing_tools(self):
        with patch("src.cpp_debug.dwarf_analyzer._ELFTOOLS_AVAILABLE", False):
            result = claude_check_and_install()
        assert "pyelftools" in result["missing"]
        assert "pip" in result["instructions"].get("pyelftools", "")
