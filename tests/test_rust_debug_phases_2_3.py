"""
Tests for Rust-Debug Phases 2-3

Phase 2: Borrow Checker Parser
Phase 3: Clippy Linter Integration

These tests verify the Rust debugging components work correctly,
with graceful degradation if rustc/clippy aren't installed.
"""

import pytest
from src.rust_debug import RustDebugger, REQUIRED_TOOLS
from src.rust_debug.borrow_checker import BorrowCheckerParser, RustBugPatternDetector
from src.rust_debug.clippy_linter import ClippyLinter, CliPPYMerger
from src.common.interop import RiskLevel, BugSeverity


class TestBorrowCheckerParser:
    """Test Phase 2: Borrow Checker Parser"""
    
    def test_parser_initialization(self):
        """Parser should initialize without errors."""
        parser = BorrowCheckerParser()
        assert parser is not None
    
    def test_parser_detects_rustc_availability(self):
        """Parser should check if rustc is available."""
        parser = BorrowCheckerParser()
        # rustc_available is True or False depending on installation
        assert isinstance(parser.rustc_available, bool)
    
    def test_graceful_degradation_no_rustc(self):
        """Parser should return empty results if rustc unavailable."""
        parser = BorrowCheckerParser()
        result = parser.parse_borrow_checker_output("fn main() {}")
        
        assert isinstance(result, dict)
        assert "errors" in result
        assert "warnings" in result
        assert "rustc_available" in result
        
        if not result["rustc_available"]:
            assert result["errors"] == []
            assert result["warnings"] == []


class TestBorrowCheckerPatternDetector:
    """Test Pattern Detection from borrow checker output"""
    
    def test_detector_initialization(self):
        """Detector should initialize."""
        detector = RustBugPatternDetector()
        assert detector is not None
        assert len(detector.PATTERNS) > 0
    
    def test_detect_double_borrow_pattern(self):
        """Should detect double borrow pattern."""
        detector = RustBugPatternDetector()
        
        errors = [
            {
                "type": "double_borrow",
                "message": "Cannot borrow as mutable",
                "line": 5,
                "category": "borrow_check",
            }
        ]
        
        patterns = detector.detect_patterns(errors, [])
        assert len(patterns) > 0
        assert patterns[0].pattern_type == "double_borrow"
    
    def test_detect_use_after_move_pattern(self):
        """Should detect use-after-move pattern."""
        detector = RustBugPatternDetector()
        
        errors = [
            {
                "type": "use_after_move",
                "message": "Use of moved value",
                "line": 10,
                "category": "borrow_check",
            }
        ]
        
        patterns = detector.detect_patterns(errors, [])
        assert len(patterns) > 0
        assert patterns[0].pattern_type == "use_after_move"

    def test_uncategorized_errors_are_filtered_not_detected(self):
        """detect_patterns() only surfaces errors tagged category="borrow_check"
        (see borrow_checker.py's DEPENDENCY_RESOLUTION_CODES / _parse_diagnostic).

        Regression coverage: v2.9.5 added this category filter to keep
        dependency-resolution noise (unresolved crate/import/trait, no fn main)
        out of borrow-checker findings, but it silently made detect_patterns()
        require a "category" key with no error or warning for callers who
        build error dicts by hand and omit it -- exactly what
        test_detect_double_borrow_pattern/test_detect_use_after_move_pattern
        above did until this fix. This test locks in the actual, current
        contract: no "category" key (or any value other than "borrow_check")
        means "not detected", not "detected via a default". Any caller
        constructing error dicts directly (as these tests do) must include
        category="borrow_check" explicitly, per _parse_diagnostic's real output.
        """
        detector = RustBugPatternDetector()

        errors = [
            {
                "type": "double_borrow",
                "message": "Cannot borrow as mutable",
                "line": 5,
                # no "category" key at all
            }
        ]
        patterns = detector.detect_patterns(errors, [])
        assert patterns == []

        errors_wrong_category = [
            {
                "type": "double_borrow",
                "message": "Cannot borrow as mutable",
                "line": 5,
                "category": "dependency_resolution",
            }
        ]
        patterns = detector.detect_patterns(errors_wrong_category, [])
        assert patterns == []


class TestClippyLinter:
    """Test Phase 3: Clippy Linter Integration"""
    
    def test_linter_initialization(self):
        """Linter should initialize."""
        linter = ClippyLinter()
        assert linter is not None
    
    def test_linter_detects_clippy_availability(self):
        """Linter should check if clippy is available."""
        linter = ClippyLinter()
        assert isinstance(linter.clippy_available, bool)
    
    def test_graceful_degradation_no_clippy(self):
        """Linter should return empty results if clippy unavailable."""
        linter = ClippyLinter()
        patterns = linter.run_clippy("fn main() {}")
        
        assert isinstance(patterns, list)
        # If clippy unavailable, should return empty list
        if not linter.clippy_available:
            assert patterns == []


class TestCliPPYMerger:
    """Test merging borrow checker and clippy results"""
    
    def test_merger_deduplicates(self):
        """Merger should avoid duplicate patterns."""
        from src.common.interop import BugPattern, ComponentType, LanguageType
        
        borrow_patterns = [
            BugPattern(
                pattern_type="double_borrow",
                severity=BugSeverity.CRITICAL,
                location="line 5",
                description="Double borrow",
                component=ComponentType.RUST_DEBUG,
                language=LanguageType.RUST,
            )
        ]
        
        clippy_patterns = [
            BugPattern(
                pattern_type="clippy_unused",
                severity=BugSeverity.LOW,
                location="line 10",
                description="Unused variable",
                component=ComponentType.RUST_DEBUG,
                language=LanguageType.RUST,
            )
        ]
        
        merged = CliPPYMerger.merge_results(borrow_patterns, clippy_patterns)
        
        # Should have both patterns
        assert len(merged) == 2
        
        # Critical should come first
        assert merged[0].severity == BugSeverity.CRITICAL
    
    def test_merger_sorts_by_severity(self):
        """Merged patterns should be sorted by severity."""
        from src.common.interop import BugPattern, ComponentType, LanguageType
        
        patterns = [
            BugPattern(
                pattern_type="low",
                severity=BugSeverity.LOW,
                location="line 1",
                description="Low",
                component=ComponentType.RUST_DEBUG,
                language=LanguageType.RUST,
            ),
            BugPattern(
                pattern_type="critical",
                severity=BugSeverity.CRITICAL,
                location="line 2",
                description="Critical",
                component=ComponentType.RUST_DEBUG,
                language=LanguageType.RUST,
            ),
        ]
        
        merged = CliPPYMerger.merge_results(patterns, [])
        
        assert merged[0].severity == BugSeverity.CRITICAL
        assert merged[1].severity == BugSeverity.LOW


class TestRustDebugger:
    """Test integrated RustDebugger (Phases 2-3)"""
    
    def test_debugger_initialization(self):
        """RustDebugger should initialize."""
        debugger = RustDebugger()
        assert debugger is not None
        assert debugger.borrow_checker is not None
        assert debugger.clippy is not None
    
    def test_debug_simple_code_no_errors(self):
        """Debugging valid code should return low risk."""
        debugger = RustDebugger()
        
        code = """
fn add(a: i32, b: i32) -> i32 {
    a + b
}

fn main() {
    let result = add(5, 3);
    println!("{}", result);
}
"""
        
        report = debugger.debug(code)
        
        # Should have executed phases
        assert "static" in report.phases_executed or "runtime" in report.phases_executed
        
        # Valid code should have low or medium risk
        assert report.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
    
    def test_phase_1_runtime(self):
        """Phase 1 (runtime) should return a report."""
        debugger = RustDebugger()
        
        code = "fn main() { println!(\"Hello\"); }"
        report = debugger.phase_1_runtime(code)
        
        assert report is not None
        assert hasattr(report, 'risk_level')
        assert hasattr(report, 'bug_patterns')
    
    def test_phase_3_design_detects_unsafe(self):
        """Phase 3 should detect unsafe blocks."""
        debugger = RustDebugger()
        
        code = """
fn main() {
    unsafe {
        // unsafe code
    }
}
"""
        
        design_issues = debugger.phase_3_design(code)
        
        assert design_issues is not None
        assert design_issues["unsafe_blocks"] >= 1
    
    def test_phase_3_design_detects_unwrap(self):
        """Phase 3 should detect unwrap() calls."""
        debugger = RustDebugger()
        
        code = "let x = Some(5).unwrap();"
        design_issues = debugger.phase_3_design(code)
        
        assert design_issues is not None
        assert design_issues["unwrap_calls"] >= 1
    
    def test_phase_3_design_detects_panic(self):
        """Phase 3 should detect panic!() calls."""
        debugger = RustDebugger()
        
        code = 'if x < 0 { panic!("negative"); }'
        design_issues = debugger.phase_3_design(code)
        
        assert design_issues is not None
        assert design_issues["panic_calls"] >= 1


class TestAcceptanceCriteria:
    """Acceptance criteria for Phases 2-3"""
    
    def test_required_tools_defined(self):
        """REQUIRED_TOOLS should be defined for Claude."""
        assert len(REQUIRED_TOOLS) >= 2
        
        tool_names = [t["name"] for t in REQUIRED_TOOLS]
        assert "rustc" in tool_names
        assert "clippy" in tool_names
    
    def test_rustc_install_instructions_present(self):
        """Should have install instructions for rustc."""
        rustc_tool = next((t for t in REQUIRED_TOOLS if t["name"] == "rustc"), None)
        assert rustc_tool is not None
        assert "install" in rustc_tool
        assert len(rustc_tool["install"]) > 0
    
    def test_clippy_install_instructions_present(self):
        """Should have install instructions for clippy."""
        clippy_tool = next((t for t in REQUIRED_TOOLS if t["name"] == "clippy"), None)
        assert clippy_tool is not None
        assert "install" in clippy_tool
        assert len(clippy_tool["install"]) > 0
    
    def test_all_phases_implemented(self):
        """All Rust phases should be implemented."""
        debugger = RustDebugger()
        
        # Phase 0
        assert hasattr(debugger, 'phase_0_static')
        assert callable(debugger.phase_0_static)
        
        # Phase 1
        assert hasattr(debugger, 'phase_1_runtime')
        assert callable(debugger.phase_1_runtime)
        
        # Phase 2
        assert hasattr(debugger, 'phase_2_formal')
        assert callable(debugger.phase_2_formal)
        
        # Phase 3
        assert hasattr(debugger, 'phase_3_design')
        assert callable(debugger.phase_3_design)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
