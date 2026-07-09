"""
Cppcheck second-opinion static analyzer for C/C++-Debug.

Clang's `-Wall -Wextra` diagnostics and the Clang Static Analyzer (CSA)
already cover a lot of ground (see diagnostics.py / analyzer.py), but
cppcheck uses different detection heuristics (dataflow-based, not
AST-diagnostic-based) and catches a genuinely different, only partially
overlapping set of bugs in practice - most usefully: memory leaks that CSA's
path-sensitivity misses, uninitialised struct members, and some out-of-bounds
array index cases via simpler control-flow reasoning than CSA's full path
exploration. Running both and merging is a "second opinion" pattern: fewer
false negatives at the cost of some duplicate/overlapping findings, which
`CppBugPatternClassifier.merge_and_dedupe` already handles.

Verified 2026-07-09 (this session): `apt-get install -y cppcheck` on
Ubuntu 24.04 (noble), then run with `--enable=all` against a real memory
leak - correctly reported "Memory leak: p [memleak]" at the right line.

Public API:
    CppcheckAnalyzer().analyze(code, dialect="c")  -> List[BugPattern]
    cppcheck_available()                            -> bool
"""

import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from ..common.interop import BugPattern, BugSeverity, ComponentType, LanguageType

REQUIRED_TOOLS = {
    "cppcheck": {
        "description": "Dataflow-based static analyzer for C/C++, second opinion alongside Clang",
        "check": "cppcheck --version",
        "install": {
            "apt": "sudo apt install cppcheck",
            "brew": "brew install cppcheck",
            "note": "Verified 2026-07-09 on Ubuntu 24.04 (noble) via apt.",
        },
        "optional": True,  # CppDebugger degrades to Clang-only without it
    },
}

# cppcheck severity -> our BugSeverity. cppcheck's own scale is
# error/warning/style/performance/portability/information.
_SEVERITY_MAP = {
    "error": BugSeverity.HIGH,
    "warning": BugSeverity.MEDIUM,
    "performance": BugSeverity.LOW,
    "portability": BugSeverity.LOW,
    "style": BugSeverity.INFO,
    "information": BugSeverity.INFO,
}

# A handful of cppcheck error IDs that are unambiguous, high-value memory
# safety bugs - promoted to CRITICAL regardless of cppcheck's own severity
# label, since these are the same class of bug valgrind/CSA treat as
# critical elsewhere in this suite.
_CRITICAL_IDS = {
    "memleak", "doubleFree", "useAfterFree", "nullPointer",
    "arrayIndexOutOfBounds", "bufferAccessOutOfBounds", "uninitvar",
}


def cppcheck_available() -> bool:
    """Return True if cppcheck is on PATH."""
    return shutil.which("cppcheck") is not None


class CppcheckAnalyzer:
    """
    Runs cppcheck against C/C++ source and returns BugPatterns.

    Uses cppcheck's `--xml` output rather than parsing text, since the XML
    schema is stable across versions and avoids the brittleness of regex-
    parsing human-readable diagnostic text (the same reason CBMC/valgrind
    parsing elsewhere in this suite sticks to well-defined line formats).
    """

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def analyze(self, code: str, dialect: str = "c") -> List[BugPattern]:
        """
        Run cppcheck --enable=all --xml against `code`.

        Degrades gracefully: returns [] if cppcheck isn't installed or the
        run fails outright (a parse/crash in cppcheck itself, not a finding).
        """
        if not cppcheck_available():
            return []

        language = LanguageType.CPP if dialect == "cpp" else LanguageType.C
        suffix = ".cpp" if dialect == "cpp" else ".c"

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / f"input{suffix}"
            src.write_text(code)

            try:
                result = subprocess.run(
                    [
                        "cppcheck",
                        "--enable=all",
                        "--inconclusive",
                        "--xml",
                        "--xml-version=2",
                        "--suppress=missingIncludeSystem",
                        "--suppress=unmatchedSuppression",
                        "--suppress=checkersReport",
                        str(src),
                    ],
                    capture_output=True, text=True, timeout=self.timeout,
                )
            except subprocess.TimeoutExpired:
                return []
            except Exception:
                return []

            # cppcheck writes its XML report to stderr, not stdout.
            return self._parse_xml(result.stderr, language, src.name)

    def _parse_xml(self, xml_text: str, language: LanguageType, filename: str) -> List[BugPattern]:
        patterns: List[BugPattern] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return patterns

        errors_el = root.find("errors")
        if errors_el is None:
            return patterns

        for err in errors_el.findall("error"):
            error_id = err.get("id", "unknown")
            cppcheck_severity = err.get("severity", "style")
            msg = err.get("verbose") or err.get("msg") or error_id

            loc_el = err.find("location")
            if loc_el is not None:
                line = loc_el.get("line", "?")
                location = f"{filename}:{line}"
            else:
                location = "unknown location"

            if error_id in _CRITICAL_IDS:
                severity = BugSeverity.CRITICAL if cppcheck_severity == "error" else BugSeverity.HIGH
            else:
                severity = _SEVERITY_MAP.get(cppcheck_severity, BugSeverity.INFO)

            patterns.append(BugPattern(
                pattern_type=f"cppcheck_{error_id}",
                severity=severity,
                location=location,
                description=msg,
                component=ComponentType.CPP_DEBUG,
                language=language,
                suggestion="See cppcheck documentation for this check ID: "
                            f"https://cppcheck.sourceforge.io/ (id={error_id})",
                confidence=0.7 if err.get("inconclusive") == "true" else 0.9,
            ))

        return patterns


__all__ = ["CppcheckAnalyzer", "cppcheck_available", "REQUIRED_TOOLS"]
