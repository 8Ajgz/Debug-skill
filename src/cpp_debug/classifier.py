"""
Classifies raw Clang compiler diagnostics and Static Analyzer findings into
debug-suite's unified BugPattern format, mirroring rust_debug's
RustBugPatternDetector / ClippyLinter classification approach.
"""
from typing import Any, Dict, List

from ..common.interop import BugPattern, BugSeverity, ComponentType, LanguageType


# Maps a clang -W flag (or substring of the message when no flag is present,
# e.g. hard errors) to a (pattern_type, severity) pair.
_WARNING_FLAG_MAP = {
    "-Wuninitialized": ("uninitialized_variable", BugSeverity.CRITICAL),
    "-Wmaybe-uninitialized": ("uninitialized_variable", BugSeverity.CRITICAL),
    "-Wnull-dereference": ("null_dereference", BugSeverity.CRITICAL),
    "-Wreturn-type": ("missing_return", BugSeverity.HIGH),
    "-Wsign-compare": ("sign_comparison", BugSeverity.MEDIUM),
    "-Wformat": ("format_string_mismatch", BugSeverity.HIGH),
    "-Wformat-security": ("format_string_mismatch", BugSeverity.CRITICAL),
    "-Wunused-variable": ("unused_variable", BugSeverity.LOW),
    "-Wunused-parameter": ("unused_parameter", BugSeverity.LOW),
    "-Wunused-value": ("unused_value", BugSeverity.LOW),
    "-Wdeprecated-declarations": ("deprecated_api", BugSeverity.LOW),
    "-Wimplicit-function-declaration": ("implicit_declaration", BugSeverity.HIGH),
    "-Wincompatible-pointer-types": ("type_mismatch", BugSeverity.HIGH),
}

# Maps a Clang Static Analyzer checker name to (pattern_type, severity).
_ANALYZER_CHECKER_MAP = {
    "core.NullDereference": ("null_dereference", BugSeverity.CRITICAL),
    "core.DivideZero": ("division_by_zero", BugSeverity.CRITICAL),
    "core.UndefinedBinaryOperatorResult": ("undefined_behavior", BugSeverity.CRITICAL),
    "core.uninitialized.Assign": ("uninitialized_variable", BugSeverity.CRITICAL),
    "core.uninitialized.Branch": ("uninitialized_variable", BugSeverity.CRITICAL),
    "unix.Malloc": ("memory_leak", BugSeverity.HIGH),
    "cplusplus.NewDelete": ("memory_leak", BugSeverity.HIGH),
    "cplusplus.NewDeleteLeaks": ("memory_leak", BugSeverity.HIGH),
    "deadcode.DeadStores": ("dead_store", BugSeverity.LOW),
    "security.insecureAPI.strcpy": ("unsafe_string_api", BugSeverity.HIGH),
    "alpha.security.ArrayBound": ("buffer_overflow", BugSeverity.CRITICAL),
}


class CppBugPatternClassifier:
    """Converts raw diagnostic/analyzer dicts into BugPattern objects."""

    def classify_diagnostics(
        self,
        diagnostics: Dict[str, Any],
        dialect: str,
    ) -> List[BugPattern]:
        """Classify compiler errors/warnings from DiagnosticsCompiler output."""
        language = LanguageType.CPP if dialect == "cpp" else LanguageType.C
        patterns: List[BugPattern] = []

        for error in diagnostics.get("errors", []):
            patterns.append(BugPattern(
                pattern_type="compile_error",
                severity=BugSeverity.CRITICAL,
                location=f"line {error['line']}",
                description=error["message"],
                component=ComponentType.CPP_DEBUG,
                language=language,
            ))

        for warning in diagnostics.get("warnings", []):
            flag = warning.get("flag", "")
            pattern_type, severity = _WARNING_FLAG_MAP.get(flag, ("clang_warning", BugSeverity.MEDIUM))
            patterns.append(BugPattern(
                pattern_type=pattern_type,
                severity=severity,
                location=f"line {warning['line']}",
                description=warning["message"],
                component=ComponentType.CPP_DEBUG,
                language=language,
                suggestion=f"Compile with {flag} to see this warning" if flag else "",
            ))

        return patterns

    def classify_analyzer_findings(
        self,
        analyzer_result: Dict[str, Any],
        dialect: str,
    ) -> List[BugPattern]:
        """Classify Clang Static Analyzer findings into BugPattern objects."""
        language = LanguageType.CPP if dialect == "cpp" else LanguageType.C
        patterns: List[BugPattern] = []

        for finding in analyzer_result.get("findings", []):
            checker = finding.get("checker", "")
            pattern_type, severity = _ANALYZER_CHECKER_MAP.get(
                checker, ("static_analysis_finding", BugSeverity.MEDIUM)
            )
            patterns.append(BugPattern(
                pattern_type=pattern_type,
                severity=severity,
                location=f"line {finding['line']}",
                description=finding["message"],
                component=ComponentType.CPP_DEBUG,
                language=language,
                suggestion=f"Clang Static Analyzer checker: {checker}" if checker else "",
                confidence=0.85,  # path-sensitive but can have false positives
            ))

        return patterns

    @staticmethod
    def merge_and_dedupe(patterns: List[BugPattern]) -> List[BugPattern]:
        """Deduplicate by (location, pattern_type) and sort by severity."""
        severity_order = {
            BugSeverity.CRITICAL: 0,
            BugSeverity.HIGH: 1,
            BugSeverity.MEDIUM: 2,
            BugSeverity.LOW: 3,
            BugSeverity.INFO: 4,
        }
        seen = set()
        deduped = []
        for p in patterns:
            key = (p.location, p.pattern_type)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(p)
        return sorted(deduped, key=lambda p: severity_order.get(p.severity, 5))
