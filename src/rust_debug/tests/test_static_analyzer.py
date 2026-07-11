"""
Tests for rust_debug/static_analyzer.py (Phase 0).

Regression coverage for the fix documented in STUBS.md: `phase_0_static()`
and the inline `phase_0_ok = True  # Placeholder` in `debug()` used to
always return/assign True regardless of the code passed in, with no real
analysis running at all. These tests check the replacement actually does
real, input-dependent work.
"""

from ..static_analyzer import RustStaticAnalyzer
from ..phases import RustDebugger
from ...common.interop import BugSeverity


class TestDelimiterBalance:
    def test_balanced_code_passes(self):
        code = "fn add(a: i32, b: i32) -> i32 { a + b }"
        result = RustStaticAnalyzer().analyze(code)
        assert result.delimiter_balanced is True
        assert result.passed is True

    def test_unclosed_brace_fails(self):
        code = "fn main() { let x = 5;"
        result = RustStaticAnalyzer().analyze(code)
        assert result.delimiter_balanced is False
        assert result.passed is False
        assert any(p.severity == BugSeverity.CRITICAL for p in result.patterns)

    def test_mismatched_delimiter_fails(self):
        code = "fn main() { let x = (5]; }"
        result = RustStaticAnalyzer().analyze(code)
        assert result.delimiter_balanced is False

    def test_braces_inside_string_do_not_count(self):
        """A brace character inside a string literal must not be treated
        as a real delimiter - regression check for the string-stripping
        pass in _strip_strings_and_comments."""
        code = 'fn main() { let s = "unbalanced { brace in a string"; }'
        result = RustStaticAnalyzer().analyze(code)
        assert result.delimiter_balanced is True

    def test_braces_inside_line_comment_do_not_count(self):
        code = "fn main() { let x = 5; // unclosed { comment\n}"
        result = RustStaticAnalyzer().analyze(code)
        assert result.delimiter_balanced is True

    def test_braces_inside_block_comment_do_not_count(self):
        code = "fn main() { /* { unbalanced */ let x = 5; }"
        result = RustStaticAnalyzer().analyze(code)
        assert result.delimiter_balanced is True


class TestIncompleteCodeMarkers:
    def test_todo_macro_detected(self):
        code = "fn foo() -> i32 { todo!() }"
        result = RustStaticAnalyzer().analyze(code)
        assert result.incomplete_code_markers
        assert any(p.pattern_type == "INCOMPLETE_CODE" for p in result.patterns)
        assert result.passed is False

    def test_unimplemented_macro_detected(self):
        code = "fn foo() -> i32 { unimplemented!() }"
        result = RustStaticAnalyzer().analyze(code)
        assert any("unimplemented" in m for m in result.incomplete_code_markers)

    def test_unreachable_macro_detected(self):
        code = "match x { 1 => 1, _ => unreachable!() }"
        result = RustStaticAnalyzer().analyze(code)
        assert any("unreachable" in m for m in result.incomplete_code_markers)

    def test_clean_code_has_no_markers(self):
        code = "fn add(a: i32, b: i32) -> i32 { a + b }"
        result = RustStaticAnalyzer().analyze(code)
        assert result.incomplete_code_markers == []

    def test_todo_in_comment_not_flagged_as_macro(self):
        """A plain-English 'todo' in a comment (not the todo!() macro
        call) should not be flagged - only the macro invocation is a real
        incomplete-code signal."""
        code = "fn add(a: i32, b: i32) -> i32 { // todo clean this up\n a + b }"
        result = RustStaticAnalyzer().analyze(code)
        assert result.incomplete_code_markers == []


class TestLintSuppressions:
    def test_allow_attribute_recorded(self):
        code = "#[allow(dead_code)]\nfn unused() {}"
        result = RustStaticAnalyzer().analyze(code)
        assert "dead_code" in result.lint_suppressions

    def test_no_suppressions_when_absent(self):
        code = "fn add(a: i32, b: i32) -> i32 { a + b }"
        result = RustStaticAnalyzer().analyze(code)
        assert result.lint_suppressions == []


class TestRustDebuggerIntegration:
    """Confirms Phase 0 is actually wired into RustDebugger.debug() and
    phase_0_static(), not just implemented standalone and orphaned."""

    def test_phase_0_static_reflects_real_analysis(self):
        debugger = RustDebugger()
        assert debugger.phase_0_static("fn add(a: i32, b: i32) -> i32 { a + b }") is True
        assert debugger.phase_0_static("fn main() { let x = 5;") is False

    def test_debug_flags_unbalanced_delimiters_as_critical(self):
        debugger = RustDebugger()
        report = debugger.debug("fn main() { let x = 5;")
        assert report.risk_level.name == "CRITICAL"
        assert any(p.pattern_type == "UNBALANCED_DELIMITERS" for p in report.bug_patterns)

    def test_debug_flags_incomplete_code_as_high(self):
        debugger = RustDebugger()
        report = debugger.debug("fn foo() -> i32 { todo!() }\nfn main() { foo(); }")
        assert any(p.pattern_type == "INCOMPLETE_CODE" for p in report.bug_patterns)

    def test_debug_static_phase_always_in_phases_executed(self):
        """Phase 0 must show up in phases_executed regardless of whether
        rustc/clippy are installed - it's the one phase with no external
        tool dependency."""
        debugger = RustDebugger()
        report = debugger.debug("fn add(a: i32, b: i32) -> i32 { a + b }")
        assert "static" in report.phases_executed
