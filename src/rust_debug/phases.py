"""
Rust-Debug Phases 0-3

Phase 0: Static analysis (delimiter balance + incomplete-code markers;
         see static_analyzer.py for why this is regex-based rather than
         a real AST, and STUBS.md for the placeholder this replaced)
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
from .static_analyzer import RustStaticAnalyzer
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
        self.static_analyzer = RustStaticAnalyzer()
    
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
        
        # Phase 0: Static analysis (delimiter balance + incomplete-code
        # markers) - see static_analyzer.py. Runs regardless of rustc
        # availability, so it's the only phase that gives any signal at
        # all when the Rust toolchain isn't installed.
        static_result = self.static_analyzer.analyze(code)
        static_patterns = static_result.patterns

        # Phase 1: Runtime/Compilation (borrow checker + clippy)
        borrow_output = self.borrow_checker.parse_borrow_checker_output(code)
        borrow_errors = borrow_output.get('errors', [])
        clippy_patterns = self.clippy.run_clippy(code)

        # Split diagnostics by category. "borrow_check" errors are real
        # ownership/lifetime violations. "dependency_resolution" errors
        # (missing crate, unresolved import, trait not in scope, no main
        # fn) fire whenever a file is compiled standalone without its
        # Cargo dependency graph — the normal case for any real-world Rust
        # file pulled out of its crate — and must never be reported or
        # risk-classified as memory-safety findings.
        true_borrow_errors = [e for e in borrow_errors if e.get('category') == 'borrow_check']
        dependency_errors = [e for e in borrow_errors if e.get('category') == 'dependency_resolution']

        # Tool availability (parse_borrow_checker_output/run_clippy degrade
        # silently to empty results when the tool isn't installed, so the
        # only way to tell "clean" apart from "never ran" is to check these).
        rustc_available = borrow_output.get('rustc_available', False)
        clippy_available = self.clippy.clippy_available
        both_available = rustc_available and clippy_available

        # Whether borrow-checking was actually verifiable: rustc ran, but
        # if it never got past crate/import resolution, it never reached
        # the borrow checker at all, so a "no violations" result would be
        # meaningless, not reassuring.
        borrow_check_verifiable = rustc_available and not dependency_errors

        # Convert to patterns (dependency-resolution errors are excluded
        # inside detect_patterns; they are not memory-safety findings)
        borrow_patterns = self.borrow_patterns.detect_patterns(
            borrow_output.get('errors', []),
            borrow_output.get('warnings', []),
        )

        # Merge patterns (static-analysis findings first, since an
        # unbalanced-delimiter CRITICAL should be visible before anything
        # borrow-checker/clippy-derived)
        all_patterns = static_patterns + self.merger.merge_results(borrow_patterns, clippy_patterns)

        # Classify risk. Real borrow-check errors always drive CRITICAL.
        # Static-analysis findings (unbalanced delimiters, todo!()/
        # unimplemented!()) participate at their own severity like any
        # other pattern — dependency-resolution errors are the only
        # category excluded, since they say nothing about the code itself.
        if true_borrow_errors or any(p.severity == BugSeverity.CRITICAL for p in static_patterns):
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
        # underlying tool never executed) — and, specifically for Rust,
        # only if rustc actually reached the borrow checker rather than
        # stopping at unresolved crates/imports.
        if true_borrow_errors:
            report.confidence_score = 0.8
        elif not borrow_check_verifiable:
            # rustc ran but never reached the borrow checker (dependency
            # resolution failed first) — low confidence regardless of
            # clippy, since the headline "borrow checker" analysis is
            # unverified, not clean.
            report.confidence_score = 0.2
        elif both_available:
            report.confidence_score = 0.95
        elif rustc_available or clippy_available:
            report.confidence_score = 0.4
        else:
            report.confidence_score = 0.0

        # Summary
        if true_borrow_errors:
            report.summary = f"❌ Compilation error: {len(true_borrow_errors)} borrow checker violation(s)"
        elif dependency_errors:
            report.summary = (
                f"⚠️  Borrow checker not verified: {len(dependency_errors)} dependency/import "
                "resolution error(s) (missing crate, unresolved import, or similar). This file "
                "was compiled standalone without its Cargo dependency graph, so rustc never "
                "reached the borrow checker — this is not a memory-safety finding, and a clean "
                "result here should not be read as 'no borrow-check issues.'"
            )
        elif all_patterns:
            source = "static analysis" if (static_patterns and not (rustc_available or clippy_available)) else "Rust borrow checker + Clippy + static analysis"
            report.summary = f"⚠️  {len(all_patterns)} issue(s) detected ({source})"
        elif both_available:
            report.summary = "✅ No borrow checker, Clippy, or static-analysis violations"
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
                "analysis was performed (static analysis ran and found no issues, but this "
                "does not indicate the code is clean; install the Rust toolchain, see "
                "rust_debug/setup.py, to get real borrow-checker/lint analysis)."
            )

        return report
    
    def phase_0_static(self, code: str) -> bool:
        """Phase 0: Static analysis (delimiter balance + incomplete-code
        markers, see static_analyzer.py). Returns whether the code passed
        (no unbalanced delimiters and no todo!()/unimplemented!()/
        unreachable!() markers) — call `self.static_analyzer.analyze(code)`
        directly for the full StaticAnalysisResult with findings/patterns.
        """
        return self.static_analyzer.analyze(code).passed
    
    def phase_1_runtime(self, code: str) -> UnifiedDebugReport:
        """
        Phase 1: Compilation diagnostics (borrow checker + clippy).
        
        This is the real debugging layer for Rust.
        """
        return self.debug(code)
    
    def phase_2_formal(self, code: str) -> Optional[dict]:
        """Phase 2: Formal verification of Rust contracts via PyProver.

        When PyProverBridge is available, delegates verification to it
        directly (bridge decides internally how to treat missing contracts).
        When the bridge is unavailable, falls back to the local
        ContractVerifier + Z3 and returns None if no ``// Pre:`` / ``// Post:``
        annotations are found at all.
        """
        try:
            from ..common.pyprover_bridge import PyProverBridge
            bridge = PyProverBridge()
            if not bridge.is_available():
                # Fall back to local ContractVerifier directly
                from ..pyprover.contract_verifier import ContractVerifier
                contract = ContractVerifier.parse_contract(code)
                if not (contract.preconditions or contract.postconditions):
                    return None
                raw = ContractVerifier.verify_contract(code, contract)
                return {
                    "verified": raw["verified"],
                    "details": raw["details"],
                    "source": "local_contract_verifier",
                }
            report = bridge.verify(code, "rust")
            if report is None:
                return None
            return {
                "verified": report.risk_level.name == "LOW",
                "risk_level": report.risk_level.name,
                "confidence": report.confidence_score,
                "details": [report.summary],
                "source": "pyprover_bridge",
            }
        except Exception as e:
            return {"verified": False, "error": str(e), "source": "phase_2_formal"}
    
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
