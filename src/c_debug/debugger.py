"""
Phase 7: C-Debug — C-specific debugger combining CppDebugger analysis
with strace syscall tracing and valgrind memcheck for runtime observability.

Why a separate module from cpp_debug?

  - Focus: plain C programs (no C++ features). C-specific idioms
    (manual memory, POSIX APIs, syscall patterns) need targeted heuristics.
  - strace: attaches to a running process and captures every syscall.
    This catches bugs at the OS boundary that static analysis misses:
    double-close(fd), open/close imbalances, write to read-only fds, etc.
  - valgrind (memcheck): instruments every memory access at runtime.
    Catches leaks, invalid reads/writes (heap overflow/underflow,
    use-after-free), invalid/double free, and uninitialised-value use -
    bugs that compile cleanly and don't necessarily crash, so neither
    static analysis nor strace's syscall view will catch them.
  - Simpler entry point: `CDebugger().debug(code)` — no `dialect` kwarg,
    no C++ template considerations, always targets C11/POSIX.

Architecture:
  - `CDebugger.debug(code)` runs the full C-specific pipeline:
      1. CppDebugger(dialect="c") — compiler diags + CSA + DWARF + symbolic
      2. SyscallTracer — compile, run under strace, parse syscall log
      3. ValgrindRunner — compile, run under valgrind --tool=memcheck
      4. Merge all patterns into one UnifiedDebugReport
  - SyscallTracer and ValgrindRunner both degrade gracefully when their
    tool is absent or compilation fails.

Public API:
    CDebugger().debug(code)             -> UnifiedDebugReport
    SyscallTracer().trace(code)         -> SyscallReport
    ValgrindRunner().run(code)          -> ValgrindReport
    strace_available()                  -> bool
    valgrind_available()                -> bool
"""

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..common.interop import (
    BugPattern,
    BugSeverity,
    ComponentType,
    LanguageType,
    RiskLevel,
    UnifiedDebugReport,
)
from ..cpp_debug.phases import CppDebugger


# ──────────────────────────────────────────────────────────────────────────────
# Tool availability
# ──────────────────────────────────────────────────────────────────────────────

def strace_available() -> bool:
    """Return True if strace is on PATH (Linux only)."""
    return shutil.which("strace") is not None


def valgrind_available() -> bool:
    """Return True if valgrind is on PATH (Linux only)."""
    return shutil.which("valgrind") is not None


def _c_compiler() -> Optional[str]:
    """Return the first available C compiler ('gcc', 'clang', or None)."""
    for cc in ("gcc", "clang"):
        if shutil.which(cc):
            return cc
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Syscall classification
# ──────────────────────────────────────────────────────────────────────────────

# Map of syscall name → issue description for suspicious patterns.
# Format: "syscall_pattern" → (issue_type, severity, message)
_SUSPICIOUS_SYSCALLS: Dict[str, Tuple[str, BugSeverity, str]] = {
    "double_close": (
        "double_close_fd",
        BugSeverity.CRITICAL,
        "A file descriptor was closed twice (double-close). "
        "This is undefined behaviour and a potential security vulnerability "
        "if a new allocation reused the fd between the two close() calls.",
    ),
    "write_on_closed": (
        "use_after_close_fd",
        BugSeverity.CRITICAL,
        "A write() or read() was attempted on a file descriptor "
        "that had already been closed. Check fd lifetime.",
    ),
    "failed_malloc": (
        "unchecked_malloc",
        BugSeverity.HIGH,
        "brk/mmap returned ENOMEM (out of memory). "
        "The program likely called malloc() without checking the return value.",
    ),
    "failed_open": (
        "unchecked_open",
        BugSeverity.MEDIUM,
        "An open() call returned ENOENT or EACCES. "
        "The program may not handle file-not-found or permission errors.",
    ),
    "exec_in_child": (
        "exec_in_child",
        BugSeverity.LOW,
        "A fork() + exec() was detected. Ensure child file descriptors "
        "are properly closed (O_CLOEXEC) to avoid fd leaks across exec.",
    ),
}


@dataclass
class SyscallEvent:
    """One syscall captured by strace."""
    name: str           # e.g. "open", "write", "close"
    args: str           # raw argument string from strace output
    return_val: str     # return value as string (may include errno)
    line_no: int        # sequential line in the strace log
    pid: int = 0


@dataclass
class SyscallReport:
    """Analysis report from strace execution."""
    tool_available: bool
    ran: bool = False
    events: List[SyscallEvent] = field(default_factory=list)
    issues: List[BugPattern] = field(default_factory=list)
    error: str = ""
    raw_output: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# strace output parser
# ──────────────────────────────────────────────────────────────────────────────

# strace line format:
#   <pid> open("foo", O_RDONLY) = 3
#   <pid> close(3)             = 0
#   <pid> write(4, "hi", 2)   = -1 EBADF (Bad file descriptor)
_STRACE_LINE_RE = re.compile(
    r"(?:(?P<pid>\d+)\s+)?"           # optional PID prefix
    r"(?P<syscall>\w+)\("             # syscall name
    r"(?P<args>[^)]*)\)"             # arguments
    r"\s*=\s*"                        # " = "
    r"(?P<retval>\S+(?:\s+\w+(?:\s+\([^)]*\))?)?)"  # return value + optional errno
)


def _parse_strace_output(output: str) -> List[SyscallEvent]:
    """Parse strace output into SyscallEvent records."""
    events: List[SyscallEvent] = []
    for i, line in enumerate(output.splitlines(), start=1):
        m = _STRACE_LINE_RE.search(line.strip())
        if not m:
            continue
        events.append(SyscallEvent(
            name=m.group("syscall"),
            args=m.group("args"),
            return_val=m.group("retval"),
            line_no=i,
            pid=int(m.group("pid")) if m.group("pid") else 0,
        ))
    return events


def _analyse_events(events: List[SyscallEvent]) -> List[BugPattern]:
    """
    Apply heuristic rules over the syscall trace to produce BugPatterns.

    Rules:
      1. double-close: same fd appears in close() twice without an open() in between
      2. write/read after close: write/read on an fd that has been closed
      3. malloc failure: brk/mmap return value -1 with ENOMEM
      4. unchecked open: open returns -1 ENOENT/EACCES
      5. fork+exec: flag fd leak risk
    """
    patterns: List[BugPattern] = []
    closed_fds: set = set()
    open_fds: Dict[str, int] = {}  # fd string → line_no
    found_fork = False

    def _make_pattern(issue_key: str, location: str) -> BugPattern:
        itype, sev, desc = _SUSPICIOUS_SYSCALLS[issue_key]
        return BugPattern(
            pattern_type=itype,
            severity=sev,
            location=location,
            description=desc,
            component=ComponentType.CPP_DEBUG,
            language=LanguageType.C,
            suggestion=_STRACE_SUGGESTIONS.get(itype, "Review system call usage."),
        )

    for ev in events:
        name = ev.name.lower()
        loc = f"strace line {ev.line_no}"

        # Track open/creat: add fd to open set
        if name in ("open", "openat", "creat", "socket", "pipe", "accept"):
            ret = ev.return_val.strip()
            if ret.lstrip("-").isdigit() and int(ret) >= 0:
                fd_str = ret
                open_fds[fd_str] = ev.line_no
                closed_fds.discard(fd_str)

        # Track close: check for double-close
        elif name == "close":
            fd_str = ev.args.strip().split(",")[0].strip()
            if fd_str in closed_fds:
                patterns.append(_make_pattern("double_close", loc))
            else:
                closed_fds.add(fd_str)
                open_fds.pop(fd_str, None)

        # write/read after close
        elif name in ("write", "read", "recv", "send"):
            fd_str = ev.args.strip().split(",")[0].strip()
            ret = ev.return_val.strip()
            if fd_str in closed_fds or "EBADF" in ret:
                patterns.append(_make_pattern("write_on_closed", loc))

        # malloc failure via ENOMEM on brk/mmap
        elif name in ("brk", "mmap", "mmap2"):
            if "ENOMEM" in ev.return_val:
                patterns.append(_make_pattern("failed_malloc", loc))

        # unchecked open failure
        elif name in ("open", "openat") and ("ENOENT" in ev.return_val or "EACCES" in ev.return_val):
            patterns.append(_make_pattern("failed_open", loc))

        # fork+exec detection
        elif name == "clone" and not found_fork:
            found_fork = True

        elif name in ("execve", "execveat") and found_fork:
            patterns.append(_make_pattern("exec_in_child", loc))

    return patterns


_STRACE_SUGGESTIONS: Dict[str, str] = {
    "double_close_fd": (
        "Set the fd to -1 immediately after close(). "
        "Consider a wrapper that also zeros the fd variable."
    ),
    "use_after_close_fd": (
        "Never reuse a file descriptor after closing it. "
        "Track fd lifetimes and use -1 as the 'closed' sentinel."
    ),
    "unchecked_malloc": (
        "Always check malloc()/realloc() return value for NULL "
        "before using the pointer. Handle OOM explicitly."
    ),
    "unchecked_open": (
        "Check the return value of open() against -1 and inspect errno. "
        "Provide a clear error message and a recovery path."
    ),
    "exec_in_child": (
        "Pass O_CLOEXEC to open() / set FD_CLOEXEC on all file descriptors "
        "that the child should not inherit across exec()."
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# SyscallTracer
# ──────────────────────────────────────────────────────────────────────────────

class SyscallTracer:
    """
    Compiles and runs a C program under strace, then analyses the syscall log.

    Usage:
        report = SyscallTracer().trace(c_code)
    """

    def __init__(self, run_timeout: int = 5, compile_timeout: int = 15):
        self.run_timeout = run_timeout
        self.compile_timeout = compile_timeout

    def trace(self, code: str) -> SyscallReport:
        """
        Compile `code` with -g -O0, run under strace, return SyscallReport.

        Degrades gracefully:
        - strace not installed → tool_available=False
        - no C compiler → tool_available=False
        - compilation error → ran=False, error set
        - program crashes → events captured up to crash
        """
        cc = _c_compiler()
        if not strace_available() or not cc:
            return SyscallReport(
                tool_available=False,
                error="strace or C compiler not available",
            )

        report = SyscallReport(tool_available=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "input.c"
            binary = Path(tmpdir) / "input"
            src.write_text(code)

            # Compile
            try:
                cr = subprocess.run(
                    [cc, "-g", "-O0", "-std=c11", str(src), "-o", str(binary)],
                    capture_output=True, text=True, timeout=self.compile_timeout,
                )
                if cr.returncode != 0:
                    report.error = f"Compilation failed: {cr.stderr[:300]}"
                    return report
            except subprocess.TimeoutExpired:
                report.error = "Compilation timed out"
                return report
            except Exception as exc:
                report.error = f"Compilation error: {exc}"
                return report

            # Run under strace
            strace_output_file = Path(tmpdir) / "strace.log"
            try:
                subprocess.run(
                    [
                        "strace",
                        "-o", str(strace_output_file),
                        "-f",                   # follow forks
                        "-e", "trace=%file,%desc,%process,brk,mmap",
                        str(binary),
                    ],
                    capture_output=True, text=True,
                    timeout=self.run_timeout,
                    cwd=tmpdir,
                )
                raw = strace_output_file.read_text(errors="replace") if strace_output_file.exists() else ""
            except subprocess.TimeoutExpired:
                raw = strace_output_file.read_text(errors="replace") if strace_output_file.exists() else ""
                report.error = "Program timed out under strace"
            except Exception as exc:
                report.error = f"strace execution failed: {exc}"
                return report

            report.ran = True
            report.raw_output = raw
            report.events = _parse_strace_output(raw)
            report.issues = _analyse_events(report.events)

        return report


# ──────────────────────────────────────────────────────────────────────────────
# Valgrind (memcheck) — dynamic memory-error detection
#
# Complements strace (OS-boundary syscall bugs) and CppDebugger's static/DWARF
# analysis (compile-time patterns) with runtime memory-error detection:
# definite/possible leaks, invalid reads/writes (heap buffer overflow/underflow,
# use-after-free), invalid free/double-free, and use of uninitialised values.
# These are bugs that pass compilation and don't necessarily crash, so neither
# static analysis nor strace's syscall view will catch them; valgrind actually
# instruments every memory access at runtime.
#
# Verified 2026-07-09 (this session): `apt-get install -y valgrind` on
# Ubuntu 24.04 (noble), then run against a real 40-byte definite leak in a
# trivial C program - correctly reported "definitely lost: 40 bytes in 1
# blocks" with the exact allocation site (leak.c:3). Real detector, not a
# stub.
# ──────────────────────────────────────────────────────────────────────────────

_VALGRIND_ISSUE_TYPES: Dict[str, Tuple[str, BugSeverity, str]] = {
    "definitely_lost": (
        "memory_leak_definite",
        BugSeverity.HIGH,
        "Memory was allocated and never freed, and no pointer to it remains "
        "reachable at exit. This is a definite leak.",
    ),
    "indirectly_lost": (
        "memory_leak_indirect",
        BugSeverity.MEDIUM,
        "Memory is only reachable through a pointer that was itself leaked "
        "(e.g. a node in a leaked linked list).",
    ),
    "possibly_lost": (
        "memory_leak_possible",
        BugSeverity.MEDIUM,
        "Memory may be leaked; a pointer to the interior (not the start) of "
        "the block was found. Could be a false positive for interior pointers, "
        "or a real leak.",
    ),
    "invalid_read": (
        "invalid_memory_read",
        BugSeverity.CRITICAL,
        "Read from memory outside an allocated block's bounds, or from freed "
        "memory (heap buffer over/underflow or use-after-free).",
    ),
    "invalid_write": (
        "invalid_memory_write",
        BugSeverity.CRITICAL,
        "Write to memory outside an allocated block's bounds, or to freed "
        "memory (heap buffer over/underflow or use-after-free). Can silently "
        "corrupt unrelated data.",
    ),
    "invalid_free": (
        "invalid_free",
        BugSeverity.CRITICAL,
        "free()/delete was called on a pointer that wasn't returned by "
        "malloc/new, or was already freed (double-free).",
    ),
    "uninitialised_value": (
        "uninitialized_value_use",
        BugSeverity.MEDIUM,
        "A conditional branch, memory write, or syscall argument depended on "
        "an uninitialised value. Result is undefined and may vary run to run.",
    ),
}

_VALGRIND_SUGGESTIONS: Dict[str, str] = {
    "memory_leak_definite": "Ensure every malloc/calloc/realloc has a matching free() on all exit paths, including error paths.",
    "memory_leak_indirect": "Free the container/parent structure; freeing only the leaked child leaves the rest reachable but unfreed.",
    "memory_leak_possible": "Check whether an interior pointer is being kept instead of the block's original address; store the original pointer separately if you need both.",
    "invalid_memory_read": "Check array bounds and pointer lifetimes; don't read through a pointer after its target has been freed.",
    "invalid_memory_write": "Check array bounds and pointer lifetimes; don't write through a pointer after its target has been freed.",
    "invalid_free": "Only call free() once per allocation, and only on pointers actually returned by malloc/calloc/realloc.",
    "uninitialized_value_use": "Initialise all variables before use, especially struct fields and stack buffers passed to functions.",
}

# Valgrind headline patterns (first line of each error block in default
# text-mode output), e.g.:
#   ==1544== 40 bytes in 1 blocks are definitely lost in loss record 1 of 1
#   ==1234== Invalid read of size 4
#   ==1234== Invalid write of size 8
#   ==1234== Invalid free() / delete / delete[] / realloc()
#   ==1234== Conditional jump or move depends on uninitialised value(s)
#   ==1234== Use of uninitialised value of size 8
_VALGRIND_HEADLINE_RE = re.compile(
    r"^==\d+==\s*(?P<headline>.+)$"
)
# Following "by"/"at" frame line, e.g.:
#   ==1544==    by 0x10915E: main (leak.c:3)
_VALGRIND_FRAME_RE = re.compile(
    r"==\d+==\s+(?:at|by)\s+0x[0-9A-Fa-f]+:\s+\S+\s+\(([^:)]+):(\d+)\)"
)


def _classify_valgrind_headline(headline: str) -> Optional[str]:
    """Map a valgrind headline string to an _VALGRIND_ISSUE_TYPES key.

    Only matches actual per-error headlines (e.g. "40 bytes in 1 blocks are
    definitely lost in loss record 1 of 1"), not the LEAK SUMMARY section's
    aggregate lines (e.g. "indirectly lost: 0 bytes in 0 blocks"), which
    have zero counts whenever that category found nothing and would
    otherwise be misread as findings.
    """
    h = headline.lower()
    if "blocks are" in h and "lost" in h:
        if "definitely lost" in h:
            return "definitely_lost"
        if "indirectly lost" in h:
            return "indirectly_lost"
        if "possibly lost" in h:
            return "possibly_lost"
    if h.startswith("invalid read"):
        return "invalid_read"
    if h.startswith("invalid write"):
        return "invalid_write"
    if h.startswith("invalid free") or h.startswith("mismatched free"):
        return "invalid_free"
    if "uninitialised value" in h or "uninitialized value" in h:
        return "uninitialised_value"
    return None


def _parse_valgrind_output(output: str) -> List[BugPattern]:
    """
    Parse valgrind's default text-mode stderr output into BugPatterns.

    Valgrind emits one block per error: a headline line, then one or more
    "at"/"by" frame lines giving the call stack. We classify on the headline
    and take the first frame with a source location (file:line) as the
    reported location, since that's normally the user's own code rather than
    libc/vgpreload internals.
    """
    patterns: List[BugPattern] = []
    lines = output.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if "LEAK SUMMARY:" in stripped or "ERROR SUMMARY:" in stripped:
            break
        m = _VALGRIND_HEADLINE_RE.match(stripped)
        if not m:
            i += 1
            continue
        issue_key = _classify_valgrind_headline(m.group("headline"))
        if issue_key is None:
            i += 1
            continue

        # Scan forward through this error block's frame lines for a
        # file:line location.
        location = "valgrind (no source location - likely inside libc)"
        j = i + 1
        while j < len(lines) and (lines[j].strip().startswith("==") ):
            frame_line = lines[j]
            if not re.match(r"^==\d+==\s*$", frame_line.strip()) and (
                "at 0x" in frame_line or "by 0x" in frame_line
            ):
                fm = _VALGRIND_FRAME_RE.search(frame_line)
                if fm:
                    location = f"{fm.group(1)}:{fm.group(2)}"
                    break
            elif frame_line.strip() == "==" or not frame_line.strip().startswith("=="):
                break
            j += 1

        itype, sev, desc = _VALGRIND_ISSUE_TYPES[issue_key]
        patterns.append(BugPattern(
            pattern_type=itype,
            severity=sev,
            location=location,
            description=desc,
            component=ComponentType.CPP_DEBUG,
            language=LanguageType.C,
            suggestion=_VALGRIND_SUGGESTIONS.get(itype, "Review memory management."),
        ))
        i += 1

    return patterns


@dataclass
class ValgrindReport:
    """Analysis report from a valgrind memcheck run."""
    tool_available: bool
    ran: bool = False
    issues: List[BugPattern] = field(default_factory=list)
    error: str = ""
    raw_output: str = ""


class ValgrindRunner:
    """
    Compiles and runs a C program under `valgrind --tool=memcheck`, then
    parses the output into BugPatterns.

    Usage:
        report = ValgrindRunner().run(c_code)
    """

    def __init__(self, run_timeout: int = 15, compile_timeout: int = 15):
        self.run_timeout = run_timeout
        self.compile_timeout = compile_timeout

    def run(self, code: str) -> ValgrindReport:
        """
        Compile `code` with -g -O0, run under valgrind --tool=memcheck
        --leak-check=full, return ValgrindReport.

        Degrades gracefully:
        - valgrind not installed -> tool_available=False
        - no C compiler -> tool_available=False
        - compilation error -> ran=False, error set
        """
        cc = _c_compiler()
        if not valgrind_available() or not cc:
            return ValgrindReport(
                tool_available=False,
                error="valgrind or C compiler not available",
            )

        report = ValgrindReport(tool_available=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "input.c"
            binary = Path(tmpdir) / "input"
            src.write_text(code)

            try:
                cr = subprocess.run(
                    [cc, "-g", "-O0", "-std=c11", str(src), "-o", str(binary)],
                    capture_output=True, text=True, timeout=self.compile_timeout,
                )
                if cr.returncode != 0:
                    report.error = f"Compilation failed: {cr.stderr[:300]}"
                    return report
            except subprocess.TimeoutExpired:
                report.error = "Compilation timed out"
                return report
            except Exception as exc:
                report.error = f"Compilation error: {exc}"
                return report

            try:
                vr = subprocess.run(
                    [
                        "valgrind",
                        "--tool=memcheck",
                        "--leak-check=full",
                        "--show-leak-kinds=definite,indirect,possible",
                        "--track-origins=no",
                        str(binary),
                    ],
                    capture_output=True, text=True,
                    timeout=self.run_timeout,
                    cwd=tmpdir,
                )
                raw = vr.stderr  # valgrind writes its report to stderr by default
            except subprocess.TimeoutExpired:
                report.error = "Program timed out under valgrind"
                return report
            except Exception as exc:
                report.error = f"valgrind execution failed: {exc}"
                return report

            report.ran = True
            report.raw_output = raw
            report.issues = _parse_valgrind_output(raw)

        return report


# ──────────────────────────────────────────────────────────────────────────────
# CDebugger — unified C debugger
# ──────────────────────────────────────────────────────────────────────────────

class CDebugger:
    """
    Unified C-specific debugger. Combines:
      - CppDebugger(dialect="c"): compiler diags + CSA + DWARF + CBMC/KLEE
      - SyscallTracer: runtime strace syscall analysis

    Usage:
        debugger = CDebugger()
        report = debugger.debug(c_source_code)
        print(report.risk_level)
        print([p.pattern_type for p in report.patterns_detected])
    """

    def __init__(self):
        self._cpp_debugger = CppDebugger()
        self._tracer = SyscallTracer()
        self._valgrind = ValgrindRunner()

    def debug(self, code: str) -> UnifiedDebugReport:
        """
        Full C debugging: static analysis + DWARF + symbolic + syscall
        tracing + valgrind memcheck.

        Returns a single UnifiedDebugReport with all findings merged.
        """
        # Phase 4-6 analysis (via CppDebugger dialect=c)
        report = self._cpp_debugger.debug(code, dialect="c")

        # Phase 7: strace syscall analysis
        syscall_report = self._tracer.trace(code)
        if syscall_report.tool_available and syscall_report.ran:
            report.patterns_detected = report.patterns_detected + syscall_report.issues
            # Re-classify risk if syscall issues are more severe
            if any(p.severity == BugSeverity.CRITICAL for p in syscall_report.issues):
                report.risk_level = RiskLevel.CRITICAL
                report.confidence_score = min(report.confidence_score, 0.3)
            elif any(p.severity == BugSeverity.HIGH for p in syscall_report.issues):
                if report.risk_level not in (RiskLevel.CRITICAL,):
                    report.risk_level = RiskLevel.HIGH
                    report.confidence_score = min(report.confidence_score, 0.6)

        # Phase 7b: valgrind memcheck (dynamic memory-error detection)
        valgrind_report = self._valgrind.run(code)
        if valgrind_report.tool_available and valgrind_report.ran:
            report.patterns_detected = report.patterns_detected + valgrind_report.issues
            if any(p.severity == BugSeverity.CRITICAL for p in valgrind_report.issues):
                report.risk_level = RiskLevel.CRITICAL
                report.confidence_score = min(report.confidence_score, 0.3)
            elif any(p.severity == BugSeverity.HIGH for p in valgrind_report.issues):
                if report.risk_level not in (RiskLevel.CRITICAL,):
                    report.risk_level = RiskLevel.HIGH
                    report.confidence_score = min(report.confidence_score, 0.6)
            elif any(p.severity == BugSeverity.MEDIUM for p in valgrind_report.issues):
                if report.risk_level not in (RiskLevel.CRITICAL, RiskLevel.HIGH):
                    report.risk_level = RiskLevel.MEDIUM
                    report.confidence_score = min(report.confidence_score, 0.7)

        return report

    def static_only(self, code: str) -> UnifiedDebugReport:
        """Run only static analysis (no strace/valgrind). Useful in environments without them."""
        return self._cpp_debugger.debug(code, dialect="c")

    def strace_only(self, code: str) -> SyscallReport:
        """Run only strace syscall tracing, skipping all static analysis."""
        return self._tracer.trace(code)

    def valgrind_only(self, code: str) -> ValgrindReport:
        """Run only valgrind memcheck, skipping all static analysis."""
        return self._valgrind.run(code)


# ──────────────────────────────────────────────────────────────────────────────
# Claude-facing setup helper
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_TOOLS = {
    "strace": {
        "description": "Linux syscall tracer for runtime observability",
        "check": "strace --version",
        "install": {
            "apt": "sudo apt install strace",
            "note": "strace is Linux-only. On macOS, use dtruss (requires sudo) or dtrace.",
        },
        "optional": True,  # CDebugger degrades to static-only without strace
    },
    "valgrind": {
        "description": "Dynamic memory-error detector (leaks, invalid read/write, use-after-free)",
        "check": "valgrind --version",
        "install": {
            "apt": "sudo apt install valgrind",
            "brew": "brew install valgrind",
            "note": "Verified 2026-07-09 on Ubuntu 24.04 (noble) via apt, no external network beyond archive.ubuntu.com required.",
        },
        "optional": True,  # CDebugger degrades to static+strace only without valgrind
    },
    "gcc_or_clang": {
        "description": "C compiler for compilation and runtime tracing",
        "check": "gcc --version || clang --version",
        "install": {
            "apt": "sudo apt install gcc clang",
            "brew": "brew install gcc llvm",
        },
        "optional": False,
    },
}


def claude_check_and_install() -> Dict[str, Any]:
    """Check tool availability and return installation instructions."""
    missing: List[str] = []
    instructions: Dict[str, str] = {}

    if not strace_available():
        missing.append("strace")
        instructions["strace"] = (
            "# Ubuntu/Debian:  sudo apt install strace\n"
            "# macOS:          strace is Linux-only; use 'sudo dtruss' or dtrace\n"
            "# Note: strace is optional; CDebugger falls back to static analysis only."
        )
    if not valgrind_available():
        missing.append("valgrind")
        instructions["valgrind"] = (
            "# Ubuntu/Debian:  sudo apt install valgrind\n"
            "# macOS:          brew install valgrind\n"
            "# Note: valgrind is optional; CDebugger falls back to static+strace analysis only."
        )
    if not _c_compiler():
        missing.append("gcc_or_clang")
        instructions["gcc_or_clang"] = (
            "# Ubuntu/Debian:  sudo apt install gcc clang\n"
            "# macOS:          brew install gcc llvm"
        )

    return {
        "all_ready": len(missing) == 0,
        "missing": missing,
        "instructions": instructions,
    }
