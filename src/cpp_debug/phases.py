"""
CppDebugger: combines compiler diagnostics (Phase 1) + Clang Static Analyzer
(Phase 1 extension) + design review heuristics (Phase 3) for C/C++.

Mirrors rust_debug/phases.py's RustDebugger structure so master_debugger can
route to either with the same calling convention.
"""
from typing import List

from ..common.interop import (
    UnifiedDebugReport,
    BugPattern,
    BugSeverity,
    ComponentType,
    LanguageType,
    RiskLevel,
)
from .diagnostics import DiagnosticsCompiler, clang_available
from .analyzer import StaticAnalyzer
from .classifier import CppBugPatternClassifier
from .dwarf_analyzer import DWARFAnalyzer
from .symbolic_executor import SymbolicExecutor
from .cppcheck_analyzer import CppcheckAnalyzer
from .lief_analyzer import LiefBinaryAnalyzer


class CppDebugger:
    """
    C/C++-specific debugger: compiler diagnostics + static analyzer + design review.

    Usage:
        debugger = CppDebugger()
        report = debugger.debug(source_code, dialect="c")   # or dialect="cpp"
    """

    def __init__(self):
        self.compiler = DiagnosticsCompiler()
        self.analyzer = StaticAnalyzer()
        self.classifier = CppBugPatternClassifier()
        self.dwarf = DWARFAnalyzer()
        self.symbolic = SymbolicExecutor()
        self.cppcheck = CppcheckAnalyzer()
        self.lief_analyzer = LiefBinaryAnalyzer()

    def debug(self, code: str, dialect: str = "c") -> UnifiedDebugReport:
        """
        Full C/C++ debugging: diagnostics + static analysis + design review.

        Args:
            code: C or C++ source code
            dialect: "c" or "cpp"

        Returns:
            UnifiedDebugReport with all phases executed
        """
        language = LanguageType.CPP if dialect == "cpp" else LanguageType.C
        report = UnifiedDebugReport(
            component=ComponentType.CPP_DEBUG,
            language=language,
            code=code,
        )

        # Phase 1: compiler diagnostics (-Wall -Wextra)
        diagnostics = self.compiler.compile_and_diagnose(code, dialect=dialect)
        diag_patterns = self.classifier.classify_diagnostics(diagnostics, dialect)

        # Phase 1 (extended): Clang Static Analyzer (path-sensitive)
        analyzer_result = self.analyzer.analyze(code, dialect=dialect)
        analyzer_patterns = self.classifier.classify_analyzer_findings(analyzer_result, dialect)

        # Phase 3: lightweight design review (unsafe API usage, raw new/delete)
        design_patterns = self._design_review(code, dialect)

        # Phase 5: DWARF memory-layout analysis (compiled binary inspection)
        dwarf_report = self.dwarf.analyze_source(code, dialect=dialect)
        dwarf_patterns = dwarf_report.to_bug_patterns(
            language=LanguageType.CPP if dialect == "cpp" else LanguageType.C
        )

        # Phase 6: CBMC/KLEE symbolic execution (exhaustive path analysis)
        sym_report = self.symbolic.run(code, dialect=dialect)
        sym_patterns = sym_report.to_bug_patterns(
            language=LanguageType.CPP if dialect == "cpp" else LanguageType.C
        )

        # Cppcheck: dataflow-based second opinion alongside Clang diagnostics/CSA
        cppcheck_patterns = self.cppcheck.analyze(code, dialect=dialect)

        # lief: dangerous-import detection, straight from the compiled binary -
        # a capability none of the source-level analyzers above have. Binary
        # hardening posture (NX/PIE/RELRO/stack-canary) is deliberately
        # excluded here (include_hardening=False): those are properties of
        # the compiler/linker flags used, not of what this specific code
        # does, and would otherwise trip the risk classifier below on nearly
        # every input regardless of content. Call
        # LiefBinaryAnalyzer().analyze(code, include_hardening=True) directly
        # for the full hardening audit.
        lief_patterns = self.lief_analyzer.analyze(code, dialect=dialect, include_hardening=False)

        all_patterns = self.classifier.merge_and_dedupe(
            diag_patterns + analyzer_patterns + design_patterns + dwarf_patterns
            + sym_patterns + cppcheck_patterns + lief_patterns
        )
        report.patterns_detected = all_patterns

        # Risk classification
        if any(p.severity == BugSeverity.CRITICAL for p in all_patterns):
            report.risk_level = RiskLevel.CRITICAL
            report.confidence_score = 0.3
        elif any(p.severity == BugSeverity.HIGH for p in all_patterns):
            report.risk_level = RiskLevel.HIGH
            report.confidence_score = 0.6
        elif all_patterns:
            report.risk_level = RiskLevel.MEDIUM
            report.confidence_score = 0.8
        else:
            report.risk_level = RiskLevel.LOW
            report.confidence_score = 1.0 if diagnostics.get("tool_available") else 0.0

        return report

    def phase_1_runtime(self, code: str, dialect: str = "c") -> UnifiedDebugReport:
        """Compiler diagnostics + static analyzer only (no design review)."""
        return self.debug(code, dialect=dialect)

    def _design_review(self, code: str, dialect: str) -> List[BugPattern]:
        """
        Heuristic design-review pass for patterns Clang's warnings don't flag
        directly: raw owning pointers in C++, unchecked malloc, gets() usage.
        """
        language = LanguageType.CPP if dialect == "cpp" else LanguageType.C
        patterns: List[BugPattern] = []
        lines = code.splitlines()

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if "gets(" in stripped:
                patterns.append(BugPattern(
                    pattern_type="unsafe_string_api",
                    severity=BugSeverity.CRITICAL,
                    location=f"line {i}",
                    description="gets() cannot bound the input buffer and is inherently unsafe",
                    component=ComponentType.CPP_DEBUG,
                    language=language,
                    suggestion="Use fgets() with an explicit buffer size instead",
                ))
            if "strcpy(" in stripped or "strcat(" in stripped:
                patterns.append(BugPattern(
                    pattern_type="unsafe_string_api",
                    severity=BugSeverity.HIGH,
                    location=f"line {i}",
                    description="strcpy()/strcat() do not bound-check the destination buffer",
                    component=ComponentType.CPP_DEBUG,
                    language=language,
                    suggestion="Use strncpy()/strncat() or std::string in C++",
                ))
            if dialect == "cpp" and ("new " in stripped) and "delete" not in code:
                patterns.append(BugPattern(
                    pattern_type="raw_owning_pointer",
                    severity=BugSeverity.MEDIUM,
                    location=f"line {i}",
                    description="Raw 'new' with no visible matching 'delete' in this translation unit",
                    component=ComponentType.CPP_DEBUG,
                    language=language,
                    suggestion="Prefer std::unique_ptr/std::make_unique for owned allocations",
                    confidence=0.5,
                ))

        return patterns
