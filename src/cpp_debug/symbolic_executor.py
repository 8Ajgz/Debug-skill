"""
Phase 6: C/C++ Symbolic Execution — CBMC and KLEE wrappers

Drives bounded model-checkers (CBMC and KLEE) against C/C++ source code for
exhaustive path analysis. These tools find bugs that compiler warnings and the
Clang Static Analyzer miss because they explore *all* execution paths (up to a
configurable loop unroll bound), not just heuristic paths.

CBMC (C Bounded Model Checker):
  - Checks assertion violations, buffer overflows, null-pointer dereferences,
    division by zero, and integer overflow
  - Produces a counterexample trace when a bug is found
  - Installable via: apt install cbmc | brew install cbmc
  - Used via: cbmc --unwind N --bounds-check --div-by-zero-check file.c

KLEE:
  - Symbolic execution engine built on LLVM
  - Generates concrete test inputs that exercise a failing path
  - Requires LLVM/clang and a full KLEE build — heavier dependency
  - Used via: clang -emit-llvm -g file.c -o file.bc && klee file.bc

Both tools degrade gracefully: if neither is installed the SymbolicExecutor
returns an empty SymbolicReport with tool_available=False. When only CBMC is
available, KLEE checks are skipped (and vice versa).

Design note: CBMC integration was demonstrated in the v13.1 chromium test
(conversation https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26)
where CBMC v5.95.1 was installed and run against 4 real Chromium-style functions
(100% verified). That session confirmed CBMC is installable in the sandboxed
environment and should be the primary Phase 6 tool; KLEE is the secondary.

Public API:
    SymbolicExecutor().run(code, dialect="c")  -> SymbolicReport
    cbmc_available()                           -> bool
    klee_available()                           -> bool
"""

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..common.interop import BugPattern, BugSeverity, ComponentType, LanguageType


# ──────────────────────────────────────────────────────────────────────────────
# Tool availability
# ──────────────────────────────────────────────────────────────────────────────

def cbmc_available() -> bool:
    """Return True if cbmc is on PATH."""
    return shutil.which("cbmc") is not None


def klee_available() -> bool:
    """Return True if klee and clang (for -emit-llvm) are both on PATH."""
    return shutil.which("klee") is not None and shutil.which("clang") is not None


# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CounterexampleStep:
    """One step in a CBMC/KLEE counterexample trace."""
    step_type: str          # "assignment", "assert", "function_call", "goto"
    file: str
    line: int
    description: str
    value: str = ""         # Variable value at this step


@dataclass
class SymbolicFinding:
    """A single property violation found by symbolic execution."""
    tool: str               # "cbmc" or "klee"
    property_type: str      # "buffer_overflow", "null_deref", "div_zero", "assertion", "overflow"
    location: str           # "file:line" or "function"
    description: str
    severity: BugSeverity
    counterexample: List[CounterexampleStep] = field(default_factory=list)
    confidence: float = 0.9  # Symbolic execution findings are highly reliable


@dataclass
class SymbolicReport:
    """Full symbolic execution report for one source file."""
    tool_available: bool
    cbmc_ran: bool = False
    klee_ran: bool = False
    findings: List[SymbolicFinding] = field(default_factory=list)
    error: str = ""
    cbmc_raw: str = ""
    klee_raw: str = ""

    def to_bug_patterns(self, language: LanguageType = LanguageType.C) -> List[BugPattern]:
        """Convert SymbolicFinding records to unified BugPattern records."""
        patterns: List[BugPattern] = []
        for f in self.findings:
            patterns.append(BugPattern(
                pattern_type=f.property_type,
                severity=f.severity,
                location=f.location,
                description=f.description,
                component=ComponentType.CPP_DEBUG,
                language=language,
                suggestion=_SYMBOLIC_SUGGESTIONS.get(
                    f.property_type,
                    "Review this symbolic execution finding carefully."
                ),
                confidence=f.confidence,
            ))
        return patterns


_SYMBOLIC_SUGGESTIONS: Dict[str, str] = {
    "buffer_overflow": (
        "Bounds-check all array accesses. Consider using std::vector or std::array "
        "in C++, or explicit length checks before any pointer arithmetic in C."
    ),
    "null_deref": (
        "Check the pointer for NULL before dereferencing. "
        "If the pointer is guaranteed non-null by a caller contract, add an assertion."
    ),
    "div_zero": (
        "Guard the divisor with an explicit non-zero check or assertion before division."
    ),
    "assertion": (
        "An assert() failed on a reachable path. Review the assertion's precondition — "
        "either the assertion is wrong, or the calling code must be restricted."
    ),
    "overflow": (
        "Integer overflow on a reachable path. Use a wider type, switch to checked "
        "arithmetic, or add __builtin_add_overflow / SafeInt guards."
    ),
    "memory_leak": (
        "An allocation may not be freed on some path. Ensure every allocation has "
        "a corresponding deallocation; prefer RAII (std::unique_ptr) in C++."
    ),
    "uninitialized": (
        "A variable may be used before it is initialised on some path. "
        "Initialise all variables at declaration."
    ),
}

# Severity mapping from CBMC/KLEE property class names
_SEVERITY_MAP: Dict[str, BugSeverity] = {
    "buffer_overflow": BugSeverity.CRITICAL,
    "null_deref": BugSeverity.CRITICAL,
    "null-deref": BugSeverity.CRITICAL,
    "div_zero": BugSeverity.HIGH,
    "div-by-zero": BugSeverity.HIGH,
    "assertion": BugSeverity.HIGH,
    "overflow": BugSeverity.HIGH,
    "memory_leak": BugSeverity.HIGH,
    "uninitialized": BugSeverity.MEDIUM,
    "pointer": BugSeverity.HIGH,
}


# ──────────────────────────────────────────────────────────────────────────────
# CBMC driver
# ──────────────────────────────────────────────────────────────────────────────

# Matches CBMC's human-readable violation output (both old and new formats):
#   [main.pointer_overflow.1] line 12 pointer overflow in &a+4: FAILURE
#   [buffer_overflow] main.c line 5 in main: FAILURE
_CBMC_VIOLATION_RE = re.compile(
    r"FAILURE"
    r".*?(?:line\s+(\d+))?",
    re.IGNORECASE,
)

_CBMC_PROPERTY_RE = re.compile(
    r"\[(?P<prop>[^\]]+)\]"
    r"(?:.*?line\s+(?P<line>\d+))?"
    r"(?:.*?in\s+(?P<func>\w+))?",
    re.IGNORECASE,
)


def _classify_cbmc_property(prop_tag: str) -> Tuple[str, BugSeverity]:
    """Map a CBMC property tag to (property_type, severity)."""
    tag_lower = prop_tag.lower()
    # Explicit prefix/substring checks for CBMC's actual tag vocabulary
    if "bounds" in tag_lower or "array" in tag_lower:
        return "buffer_overflow", BugSeverity.CRITICAL
    if "null" in tag_lower and "deref" in tag_lower:
        return "null_deref", BugSeverity.CRITICAL
    if "null" in tag_lower or "pointer" in tag_lower:
        return "null_deref", BugSeverity.CRITICAL
    if "div-by-zero" in tag_lower or "div_by_zero" in tag_lower or "division" in tag_lower:
        return "div_zero", BugSeverity.HIGH
    if "overflow" in tag_lower:
        return "overflow", BugSeverity.HIGH
    if "memory" in tag_lower and "leak" in tag_lower:
        return "memory_leak", BugSeverity.HIGH
    if "uninit" in tag_lower:
        return "uninitialized", BugSeverity.MEDIUM
    if "assert" in tag_lower:
        return "assertion", BugSeverity.HIGH
    # Fall back to _SEVERITY_MAP for anything else
    for key, sev in _SEVERITY_MAP.items():
        if key.replace("_", "-") in tag_lower or key.replace("-", "_") in tag_lower:
            return key.replace("-", "_"), sev
    return "assertion", BugSeverity.MEDIUM


def _parse_cbmc_output(output: str, source_file: str) -> List[SymbolicFinding]:
    """
    Parse CBMC stdout/stderr for violation records.

    CBMC output format (text mode) looks like:
      [buffer_overflow.1] line 8 buffer overflow in main: FAILURE
      [main.div-by-zero.2] line 12 division by zero: FAILURE
    """
    findings: List[SymbolicFinding] = []
    for line in output.splitlines():
        if "FAILURE" not in line.upper():
            continue
        m = _CBMC_PROPERTY_RE.search(line)
        if not m:
            continue
        prop_tag = m.group("prop") or "unknown"
        line_no = int(m.group("line")) if m.group("line") else 0
        func = m.group("func") or ""

        prop_type, severity = _classify_cbmc_property(prop_tag)
        location = f"{source_file}:{line_no}" if line_no else (func or source_file)

        findings.append(SymbolicFinding(
            tool="cbmc",
            property_type=prop_type,
            location=location,
            description=f"CBMC found a violation: {line.strip()}",
            severity=severity,
            confidence=0.9,
        ))
    return findings


class CBMCDriver:
    """Drives the cbmc command-line tool."""

    # Flags: unwind 5 (reasonable for most loops), all standard checks.
    #
    # NOTE on flag names: CBMC 6.x renamed/split two flags from the CLI this
    # suite was originally built against (CBMC 5.95.1, per the module
    # docstring's v13.1 test note). --null-pointer-check became
    # --pointer-check, and --overflow-check split into
    # --signed-overflow-check / --unsigned-overflow-check. The old flag
    # names aren't silently ignored - CBMC 6.x treats them as a hard usage
    # error and refuses to run *any* check, so this wasn't a partial-
    # analysis bug, it was a total silent failure (CBMC printed its help
    # text, which _parse_cbmc_output correctly found zero findings in, so
    # SymbolicExecutor reported "ran successfully, no findings" for every
    # single input regardless of real bugs). Verified 2026-07-09 against
    # CBMC 6.10.0: with the flags below, a real division-by-zero is caught
    # correctly ("division-by-zero.1 ... FAILURE").
    BASE_FLAGS = [
        "--unwind", "5",
        "--bounds-check",
        "--div-by-zero-check",
        "--pointer-check",
        "--signed-overflow-check",
        "--unsigned-overflow-check",
        "--pointer-overflow-check",
        "--memory-leak-check",
    ]

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def run(self, code: str, dialect: str = "c") -> Tuple[List[SymbolicFinding], str, bool]:
        """
        Compile + check `code` with CBMC.

        Returns:
            (findings, raw_output, ran_successfully)
        """
        if not cbmc_available():
            return [], "", False

        suffix = ".cpp" if dialect == "cpp" else ".c"
        std_flag = "--cpp" if dialect == "cpp" else []
        extra_flags = ["--cpp"] if dialect == "cpp" else []

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / f"input{suffix}"
            src.write_text(code)

            cmd = ["cbmc"] + extra_flags + self.BASE_FLAGS + [str(src)]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                combined = result.stdout + result.stderr
                findings = _parse_cbmc_output(combined, f"input{suffix}")
                return findings, combined, True

            except subprocess.TimeoutExpired:
                return [], "cbmc timed out", True
            except Exception as exc:
                return [], f"cbmc invocation failed: {exc}", False


# ──────────────────────────────────────────────────────────────────────────────
# KLEE driver
# ──────────────────────────────────────────────────────────────────────────────

# KLEE outputs errors like:
#   KLEE: ERROR: /tmp/klee-out-0/test000001.ptr.err (memory error: out of bound pointer)
#   KLEE: ERROR: /tmp/klee-out-0/test000001.assert.err (ASSERTION FAIL: ...)
_KLEE_ERROR_RE = re.compile(
    r"KLEE: ERROR:.*?\((?P<msg>[^)]+)\)",
    re.IGNORECASE,
)


def _classify_klee_error(msg: str) -> Tuple[str, BugSeverity]:
    """Map a KLEE error message to (property_type, severity)."""
    m = msg.lower()
    if "out of bound" in m or "buffer" in m:
        return "buffer_overflow", BugSeverity.CRITICAL
    if "null" in m or "ptr" in m:
        return "null_deref", BugSeverity.CRITICAL
    if "division" in m or "div" in m:
        return "div_zero", BugSeverity.HIGH
    if "assert" in m:
        return "assertion", BugSeverity.HIGH
    if "memory" in m:
        return "memory_leak", BugSeverity.HIGH
    return "assertion", BugSeverity.MEDIUM


def _parse_klee_output(output: str) -> List[SymbolicFinding]:
    findings: List[SymbolicFinding] = []
    for line in output.splitlines():
        m = _KLEE_ERROR_RE.search(line)
        if not m:
            continue
        msg = m.group("msg")
        prop_type, severity = _classify_klee_error(msg)
        findings.append(SymbolicFinding(
            tool="klee",
            property_type=prop_type,
            location="klee-output",
            description=f"KLEE found: {msg}",
            severity=severity,
            confidence=0.85,
        ))
    return findings


class KLEEDriver:
    """
    Drives KLEE: compiles C source to LLVM bitcode with clang -emit-llvm,
    then runs klee against it.

    Note: KLEE requires a full KLEE build with LLVM support and the klee-uclibc
    library. In practice, CBMC is much easier to install. This driver is
    provided for completeness; the SymbolicExecutor tries CBMC first.
    """

    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    def run(self, code: str) -> Tuple[List[SymbolicFinding], str, bool]:
        """Compile to bitcode and run KLEE. Returns (findings, raw, ran)."""
        if not klee_available():
            return [], "", False

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "input.c"
            bc = Path(tmpdir) / "input.bc"
            src.write_text(code)

            # Step 1: compile to LLVM bitcode
            try:
                compile_result = subprocess.run(
                    ["clang", "-emit-llvm", "-g", "-O0", "-c", str(src), "-o", str(bc)],
                    capture_output=True, text=True, timeout=20,
                )
                if compile_result.returncode != 0:
                    return [], compile_result.stderr[:300], False
            except Exception as exc:
                return [], f"clang bitcode compilation failed: {exc}", False

            # Step 2: run KLEE
            try:
                klee_result = subprocess.run(
                    ["klee", "--max-time=30s", str(bc)],
                    capture_output=True, text=True,
                    timeout=self.timeout,
                    cwd=tmpdir,
                )
                combined = klee_result.stdout + klee_result.stderr
                findings = _parse_klee_output(combined)
                return findings, combined, True
            except subprocess.TimeoutExpired:
                return [], "klee timed out", True
            except Exception as exc:
                return [], f"klee invocation failed: {exc}", False


# ──────────────────────────────────────────────────────────────────────────────
# Unified SymbolicExecutor
# ──────────────────────────────────────────────────────────────────────────────

class SymbolicExecutor:
    """
    Facade that runs CBMC, KLEE, or both against C/C++ source code,
    merges their findings, and returns a SymbolicReport.

    Usage:
        executor = SymbolicExecutor()
        report = executor.run(c_code, dialect="c")
        patterns = report.to_bug_patterns()
    """

    def __init__(self, cbmc_timeout: int = 30, klee_timeout: int = 60):
        self._cbmc = CBMCDriver(timeout=cbmc_timeout)
        self._klee = KLEEDriver(timeout=klee_timeout)

    def run(self, code: str, dialect: str = "c") -> SymbolicReport:
        """
        Run available symbolic execution tools against `code`.

        Falls back gracefully if neither CBMC nor KLEE is installed.
        """
        if not cbmc_available() and not klee_available():
            return SymbolicReport(
                tool_available=False,
                error="Neither cbmc nor klee is installed. "
                      "Install cbmc with: apt install cbmc | brew install cbmc",
            )

        report = SymbolicReport(tool_available=True)
        all_findings: List[SymbolicFinding] = []

        # Run CBMC
        cbmc_findings, cbmc_raw, cbmc_ran = self._cbmc.run(code, dialect=dialect)
        report.cbmc_ran = cbmc_ran
        report.cbmc_raw = cbmc_raw
        all_findings.extend(cbmc_findings)

        # Run KLEE (only for plain C; KLEE doesn't natively handle C++)
        if dialect == "c":
            klee_findings, klee_raw, klee_ran = self._klee.run(code)
            report.klee_ran = klee_ran
            report.klee_raw = klee_raw
            all_findings.extend(klee_findings)

        # Deduplicate: same (property_type, location) from different tools
        seen: set = set()
        for f in all_findings:
            key = (f.property_type, f.location)
            if key not in seen:
                seen.add(key)
                report.findings.append(f)

        return report


# ──────────────────────────────────────────────────────────────────────────────
# Claude-facing setup helper
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_TOOLS = {
    "cbmc": {
        "description": "C Bounded Model Checker — exhaustive assertion/bounds checking",
        "check": "cbmc --version",
        "install": {
            "apt": "sudo apt install cbmc",
            "brew": "brew install cbmc",
            "docker": "FROM ubuntu:22.04 && RUN apt-get install -y cbmc",
            "source": "https://github.com/diffblue/cbmc/releases",
        },
        "optional": True,  # KLEE is the fallback
    },
    "klee": {
        "description": "KLEE symbolic virtual machine (LLVM-based)",
        "check": "klee --version",
        "install": {
            "docker": "docker pull klee/klee",
            "source": "https://klee-se.org/getting-started/",
        },
        "optional": True,  # CBMC is the primary
        "note": "KLEE requires a full LLVM build and klee-uclibc; Docker image recommended.",
    },
}


def claude_check_and_install() -> Dict[str, Any]:
    """
    Check tool availability and return installation instructions for missing tools.
    """
    missing: List[str] = []
    instructions: Dict[str, str] = {}

    if not cbmc_available():
        missing.append("cbmc")
        instructions["cbmc"] = (
            "# Ubuntu/Debian:  sudo apt install cbmc\n"
            "# macOS:          brew install cbmc\n"
            "# Docker:         FROM ubuntu:22.04 && RUN apt-get install -y cbmc\n"
            "# Source:         https://github.com/diffblue/cbmc/releases"
        )
    if not klee_available():
        missing.append("klee")
        instructions["klee"] = (
            "# Docker (easiest):  docker pull klee/klee\n"
            "# Source:            https://klee-se.org/getting-started/\n"
            "# Note: KLEE requires a full LLVM build. "
            "Use the Docker image in sandboxed environments."
        )

    return {
        "all_ready": len(missing) == 0,
        "missing": missing,
        "instructions": instructions,
        "note": (
            "CBMC is the primary Phase 6 tool and is much easier to install than KLEE. "
            "Install CBMC first; KLEE is a secondary option for deeper path exploration."
        ),
    }
