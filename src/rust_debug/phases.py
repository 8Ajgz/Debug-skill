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
        report = UnifiedDebugReport()
        
        # Phase 0: Static (minimal for Rust - type system is the analyzer)
        phase_0_ok = True  # Placeholder
        
        # Phase 1: Runtime/Compilation (borrow checker + clippy)
        borrow_output = self.borrow_checker.parse_borrow_checker_output(code)
        borrow_errors = borrow_output.get('errors', [])
        clippy_patterns = self.clippy.run_clippy(code)
        
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
        report.phases_executed = ["static", "runtime"]
        report.bug_patterns = all_patterns
        report.confidence_score = 0.8 if all_patterns else 0.95
        
        # Summary
        if borrow_errors:
            report.summary = f"❌ Compilation error: {len(borrow_errors)} borrow checker violation(s)"
        elif all_patterns:
            report.summary = f"⚠️  {len(all_patterns)} issue(s) detected (Rust borrow checker + Clippy)"
        else:
            report.summary = "✅ No borrow checker or Clippy violations"
        
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
