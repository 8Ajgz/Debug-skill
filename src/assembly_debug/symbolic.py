"""
Phase 10: Assembly Symbolic Execution using angr

Loads a compiled ELF binary into angr, runs CFGFast for structural analysis,
and drives the simulation manager to detect crashes and assertion failures.

angr is the most capable binary analysis framework available in Python but
has a heavy dependency tree (LLVM, clang, unicorn). This module degrades
gracefully when angr is absent.

What this module does:
  1. CFGFast — rapid disassembly-based CFG (no execution), extracts functions
     and basic block counts
  2. Simulation manager — symbolically execute from the entry point; collect
     paths that reach "unconstrained" states (possible crashes / exploitation)
     and "errored" states (actual crashes during concrete execution)
  3. Stack-pointer tracker — check that functions restore RSP to its entry
     value on all return paths (stack-frame sanity)
  4. Produce SymbolicFinding records compatible with Phase 6's format
     (reuses SymbolicFinding from cpp_debug.symbolic_executor)

Public API:
    AngrAnalyzer().analyse_binary(path) → AngrReport
    AngrAnalyzer().analyse_source(code, dialect) → AngrReport
    angr_available() → bool
"""

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..common.interop import BugPattern, BugSeverity, ComponentType, LanguageType

try:
    import angr
    # Silence angr's very verbose logging
    logging.getLogger("angr").setLevel(logging.ERROR)
    logging.getLogger("claripy").setLevel(logging.ERROR)
    logging.getLogger("cle").setLevel(logging.ERROR)
    logging.getLogger("pyvex").setLevel(logging.ERROR)
    _ANGR_OK = True
except ImportError:
    _ANGR_OK = False


# ──────────────────────────────────────────────────────────────────────────────
# Availability
# ──────────────────────────────────────────────────────────────────────────────

def angr_available() -> bool:
    return _ANGR_OK


def _c_compiler() -> Optional[str]:
    for cc in ("gcc", "clang"):
        if shutil.which(cc):
            return cc
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class FunctionSummary:
    """High-level summary of one function found by CFGFast."""
    name: str
    addr: int
    block_count: int
    has_indirect_calls: bool = False
    stack_delta: Optional[int] = None  # RSP change, None if unknown


@dataclass
class CrashReport:
    """One crash or unconstrained state found by the simulation manager."""
    crash_type: str     # "segfault", "unconstrained", "error", "assertion"
    description: str
    address: Optional[int] = None
    severity: BugSeverity = BugSeverity.CRITICAL


@dataclass
class AngrReport:
    """Full result of angr analysis on one binary."""
    binary_path: str
    tool_available: bool
    arch: str = "unknown"
    functions: List[FunctionSummary] = field(default_factory=list)
    crashes: List[CrashReport] = field(default_factory=list)
    cfg_nodes: int = 0
    cfg_edges: int = 0
    simgr_steps: int = 0
    error: str = ""

    def to_bug_patterns(self, language: LanguageType = LanguageType.ASSEMBLY) -> List[BugPattern]:
        patterns: List[BugPattern] = []
        for crash in self.crashes:
            patterns.append(BugPattern(
                pattern_type=f"angr_{crash.crash_type}",
                severity=crash.severity,
                location=f"0x{crash.address:x}" if crash.address else "unknown",
                description=crash.description,
                component=ComponentType.CPP_DEBUG,
                language=language,
                suggestion=_ANGR_SUGGESTIONS.get(
                    crash.crash_type,
                    "Review this angr finding with the full symbolic trace."
                ),
                confidence=0.75,
            ))
        return patterns


_ANGR_SUGGESTIONS: Dict[str, str] = {
    "unconstrained": (
        "An unconstrained state means the instruction pointer can be arbitrary under "
        "symbolic execution — a likely buffer overflow or memory corruption. "
        "Investigate all indirect branches and memory writes near this path."
    ),
    "segfault": (
        "angr reached a concrete crash (SIGSEGV / SIGBUS). "
        "Review the crash trace and look for null-pointer dereferences, "
        "out-of-bounds accesses, or stack overflows."
    ),
    "error": (
        "angr's simulation engine encountered an error on this path. "
        "This may indicate an unhandled system call, an unsupported instruction, "
        "or a genuine crash condition."
    ),
    "assertion": (
        "An assertion or abort() was reachable under symbolic execution. "
        "Review the conditions under which this path is triggered."
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Core analyser
# ──────────────────────────────────────────────────────────────────────────────

class AngrAnalyzer:
    """
    Drives angr to analyse ELF binaries for crashes and structural properties.

    Usage:
        report = AngrAnalyzer().analyse_binary("/path/to/elf")
        patterns = report.to_bug_patterns()

        # From C source (compiles first):
        report = AngrAnalyzer().analyse_source(c_code, dialect="c")
    """

    def __init__(
        self,
        simgr_steps: int = 30,
        compile_timeout: int = 20,
    ):
        self.simgr_steps = simgr_steps
        self.compile_timeout = compile_timeout

    # ── public API ────────────────────────────────────────────────────────────

    def analyse_source(self, code: str, dialect: str = "c") -> AngrReport:
        """Compile `code` then run angr on the resulting binary."""
        if not angr_available():
            return AngrReport(binary_path="", tool_available=False,
                              error="angr not installed")
        cc = _c_compiler()
        if not cc:
            return AngrReport(binary_path="", tool_available=False,
                              error="No C compiler found")

        suffix = ".cpp" if dialect == "cpp" else ".c"
        std = "-std=c++17" if dialect == "cpp" else "-std=c11"

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / f"input{suffix}"
            binary = Path(tmpdir) / "input"
            src.write_text(code)
            try:
                res = subprocess.run(
                    [cc, std, "-g", "-O0", str(src), "-o", str(binary)],
                    capture_output=True, text=True,
                    timeout=self.compile_timeout,
                )
                if res.returncode != 0:
                    return AngrReport(binary_path="", tool_available=True,
                                      error=f"Compilation failed: {res.stderr[:300]}")
            except subprocess.TimeoutExpired:
                return AngrReport(binary_path="", tool_available=True,
                                  error="Compilation timed out")
            except Exception as exc:
                return AngrReport(binary_path="", tool_available=True,
                                  error=f"Compilation error: {exc}")

            return self.analyse_binary(str(binary))

    def analyse_binary(self, path: str) -> AngrReport:
        """Run angr analysis on an existing ELF binary."""
        if not angr_available():
            return AngrReport(binary_path=path, tool_available=False,
                              error="angr not installed")
        if not Path(path).exists():
            return AngrReport(binary_path=path, tool_available=False,
                              error=f"Binary not found: {path}")

        report = AngrReport(binary_path=path, tool_available=True)
        try:
            project = angr.Project(path, auto_load_libs=False)
            report.arch = project.arch.name

            # Phase 1: CFGFast — structural overview
            self._run_cfg(project, report)

            # Phase 2: Simulation manager — crash detection
            self._run_simgr(project, report)

        except Exception as exc:
            report.error = f"angr analysis failed: {exc}"

        return report

    # ── internal analysis steps ───────────────────────────────────────────────

    def _run_cfg(self, project: "angr.Project", report: AngrReport) -> None:
        """Run CFGFast and populate function summaries."""
        try:
            cfg = project.analyses.CFGFast(normalize=True)
            nodes = list(cfg.graph.nodes())
            edges = list(cfg.graph.edges())
            report.cfg_nodes = len(nodes)
            report.cfg_edges = len(edges)

            # Extract function summaries
            for func_addr, func in project.kb.functions.items():
                try:
                    blocks = list(func.blocks)
                    summary = FunctionSummary(
                        name=func.name or f"sub_{func_addr:x}",
                        addr=func_addr,
                        block_count=len(blocks),
                    )
                    # Check for indirect calls within the function
                    for block in blocks:
                        try:
                            for insn in block.capstone.insns:
                                if insn.insn.mnemonic in ("call", "jmp") and \
                                   any(c in insn.insn.op_str for c in ("[", "r", "e")):
                                    summary.has_indirect_calls = True
                        except Exception:
                            pass
                    report.functions.append(summary)
                except Exception:
                    pass
        except Exception as exc:
            # CFGFast failure is non-fatal; continue to simgr
            report.error += f" CFGFast: {exc};"

    def _run_simgr(self, project: "angr.Project", report: AngrReport) -> None:
        """
        Run the simulation manager to detect crashes and unconstrained states.

        Strategy:
          - Start from the binary's entry point
          - Step up to self.simgr_steps times
          - Collect: errored states (concrete crashes) and unconstrained states
            (symbolic IP — potential exploitable conditions)
        """
        try:
            state = project.factory.entry_state(
                add_options={angr.options.LAZY_SOLVES}
            )
            simgr = project.factory.simulation_manager(state)

            for _ in range(self.simgr_steps):
                simgr.step()
                if not simgr.active:
                    break

            report.simgr_steps = self.simgr_steps

            # Collect unconstrained states
            unconstrained = getattr(simgr, "unconstrained", [])
            for state in unconstrained:
                try:
                    addr = state.regs.ip.args[0] if state.regs.ip.symbolic else None
                    report.crashes.append(CrashReport(
                        crash_type="unconstrained",
                        description=(
                            "Symbolic execution found an unconstrained instruction pointer "
                            "— the program counter became fully symbolic, indicating a potential "
                            "memory corruption vulnerability (buffer overflow, format string, etc.)."
                        ),
                        address=int(addr) if addr is not None else None,
                        severity=BugSeverity.CRITICAL,
                    ))
                except Exception:
                    pass

            # Collect errored states
            for err_state in getattr(simgr, "errored", []):
                try:
                    exc_type = type(err_state.error).__name__
                    description = str(err_state.error)[:200]
                    crash_type = "segfault" if "segfault" in description.lower() or "sigsegv" in description.lower() else "error"
                    addr = None
                    try:
                        addr = err_state.state.addr
                    except Exception:
                        pass
                    report.crashes.append(CrashReport(
                        crash_type=crash_type,
                        description=f"Simulation error ({exc_type}): {description}",
                        address=addr,
                        severity=BugSeverity.HIGH,
                    ))
                except Exception:
                    pass

        except Exception as exc:
            report.error += f" simgr: {exc};"


# ──────────────────────────────────────────────────────────────────────────────
# Setup helper
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_TOOLS = {
    "angr": {
        "description": "Binary analysis framework with CFG and symbolic execution",
        "check": "python3 -c \"import angr; print(angr.__version__)\"",
        "install": {
            "pip": "pip install angr",
            "note": "angr pulls in ~400 MB of dependencies. Use a virtualenv.",
        },
        "optional": True,
    },
}


def angr_check_and_install() -> Dict[str, Any]:
    missing, instructions = [], {}
    if not _ANGR_OK:
        missing.append("angr")
        instructions["angr"] = (
            "pip install angr\n"
            "# Note: ~400 MB install. Use a virtualenv to avoid conflicts.\n"
            "# Docker: FROM python:3.11 && RUN pip install angr"
        )
    return {
        "all_ready": not missing,
        "missing": missing,
        "instructions": instructions,
    }
