"""
Rust-Debug Phases 0-3

Phase 0: Static analysis (AST inspection - placeholder for v0.1)
Phase 1: Runtime/Compilation (Borrow checker + Clippy)
Phase 2: Formal verification (delegates to PyProver)
Phase 3: Design review (unsafe/panic analysis)
"""

from typing import Optional, List
from ..common.interop import (
    UnifiedDebugReport,
    Variable,
    BugPattern,
    BugSeverity,
    RiskLevel,
)
from .borrow_checker import BorrowCheckerParser, RustBugPatternDetector
from .clippy_linter import ClippyLinter, CliPPYMerger
from ..common.interop import ComponentType, LanguageType


class RustDebugger:
    """
    Rust-specific debugger combining borrow checker + Clippy + PyProver.
    
    Usage:
        debugger = RustDebugger()
        report = debugger.debug(rust_code)
    """
    
    def __init__(self):
        self.borrow_checker = BorrowCheckerParser()
        self.borrow_patterns = RustBugPatternDetector()
        self.clippy = ClippyLinter()
        self.merger = CliPPYMerger()
    
    def debug(self, code: str) -> UnifiedDebugReport:
        """
        Full Rust debugging: all phases.
        
        Args:
            code: Rust source code
        
        Returns:
            UnifiedDebugReport with all phases executed
        """
        report = UnifiedDebugReport(
            component=ComponentType.RUST_DEBUG,
            language=LanguageType.RUST,
            code=code,
        )
        
        # Phase 0: Static (minimal for Rust - type system is the analyzer)
        phase_0_ok = True  # Placeholder
        
        # Phase 1: Runtime/Compilation (borrow checker + clippy)
        borrow_output = self.borrow_checker.parse_borrow_checker_output(code)
        borrow_errors = borrow_output.get('errors', [])
        clippy_patterns = self.clippy.run_clippy(code)

        # Tool availability (parse_borrow_checker_output/run_clippy degrade
        # silently to empty results when the tool isn't installed, so the
        # only way to tell "clean" apart from "never ran" is to check these).
        rustc_available = borrow_output.get('rustc_available', False)
        clippy_available = self.clippy.clippy_available
        both_available = rustc_available and clippy_available

        # Convert to patterns
        borrow_patterns = self.borrow_patterns.detect_patterns(
            borrow_output.get('errors', []),
            borrow_output.get('warnings', []),
        )
        
        # Merge patterns
        all_patterns = self.merger.merge_results(borrow_patterns, clippy_patterns)
        
        # Classify risk
        if borrow_errors:
            risk_level = RiskLevel.CRITICAL
        elif any(p.severity == BugSeverity.HIGH for p in all_patterns):
            risk_level = RiskLevel.HIGH
        elif any(p.severity == BugSeverity.MEDIUM for p in all_patterns):
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        # Build report
        report.risk_level = risk_level
        report.phases_executed = ["static"] + (
            (["borrow_checker"] if rustc_available else [])
            + (["clippy"] if clippy_available else [])
        )
        report.bug_patterns = all_patterns

        # Confidence reflects how much real analysis actually ran, not just
        # whether patterns were found. A "no patterns" result is only
        # trustworthy if the tools that would have found them actually ran
        # (same convention as CppDebugger: confidence_score = 0.0 when the
        # underlying tool never executed).
        if all_patterns:
            report.confidence_score = 0.8
        elif both_available:
            report.confidence_score = 0.95
        elif rustc_available or clippy_available:
            report.confidence_score = 0.4
        else:
            report.confidence_score = 0.0

        # Summary
        if borrow_errors:
            report.summary = f"❌ Compilation error: {len(borrow_errors)} borrow checker violation(s)"
        elif all_patterns:
            report.summary = f"⚠️  {len(all_patterns)} issue(s) detected (Rust borrow checker + Clippy)"
        elif both_available:
            report.summary = "✅ No borrow checker or Clippy violations"
        elif rustc_available and not clippy_available:
            report.summary = (
                "⚠️  No borrow checker violations found, but clippy is not installed — "
                "lint analysis was not performed"
            )
        elif clippy_available and not rustc_available:
            report.summary = (
                "⚠️  No Clippy issues found, but rustc is not installed — "
                "borrow checker analysis was not performed"
            )
        else:
            report.summary = (
                "⚠️  rustc and clippy are not installed — no borrow checker or lint "
                "analysis was performed. This result does not indicate the code is clean; "
                "install the Rust toolchain (see rust_debug/setup.py) to get real analysis."
            )

        return report
    
    def phase_0_static(self, code: str) -> bool:
        """Phase 0: Static analysis (Rust type system does most of this)."""
        # Placeholder - Rust's type system is already the static analyzer
        return True
    
    def phase_1_runtime(self, code: str) -> UnifiedDebugReport:
        """
        Phase 1: Compilation diagnostics (borrow checker + clippy).
        
        This is the real debugging layer for Rust.
        """
        return self.debug(code)
    
    def phase_2_formal(self, code: str) -> Optional[dict]:
        """
        Phase 2: Formal verification via PyProver.
        
        Delegates to PyProver for contract verification.
        """
        # Placeholder - would call PyProver bridge
        return None
    
    def phase_3_design(self, code: str) -> Optional[dict]:
        """
        Phase 3: Design review - unsafe/panic analysis.
        """
        unsafe_blocks = code.count("unsafe")
        unwrap_calls = code.count(".unwrap()")
        panic_calls = code.count("panic!")
        
        issues = []
        if unsafe_blocks > 0:
            issues.append(f"{unsafe_blocks} unsafe block(s) - ensure memory safety")
        if unwrap_calls > 0:
            issues.append(f"{unwrap_calls} unwrap() call(s) - consider using ? operator")
        if panic_calls > 0:
            issues.append(f"{panic_calls} panic!() call(s) - prefer Result<T, E>")
        
        return {
            "unsafe_blocks": unsafe_blocks,
            "unwrap_calls": unwrap_calls,
            "panic_calls": panic_calls,
            "design_issues": issues,
        }


__all__ = ["RustDebugger"]
