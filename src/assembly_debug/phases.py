"""
AssemblyDebugger: unified facade for Phases 8-10.

Combines:
  Phase 8: Capstone disassembly + CFG construction + structural analysis
  Phase 9: Register dataflow taint analysis over the CFG
  Phase 10: angr symbolic execution on the compiled binary

Usage:
    debugger = AssemblyDebugger()

    # From raw bytes:
    report = debugger.debug_bytes(raw_bytes, arch="x86_64", base_addr=0x1000)

    # From ELF binary:
    report = debugger.debug_binary("/path/to/elf")

    # From C/C++ source (compiles, then runs all three phases):
    report = debugger.debug_source(c_code, dialect="c")

Returns a UnifiedDebugReport with all findings merged.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from ..common.interop import (
    BugPattern, BugSeverity, ComponentType, LanguageType,
    RiskLevel, UnifiedDebugReport,
)
from .disassembler import Disassembler, DisassemblyReport, capstone_available
from .cfg import CFGBuilder, CFGAnalysis, ControlFlowGraph
from .dataflow import TaintAnalyzer
from .symbolic import AngrAnalyzer, angr_available


def _c_compiler() -> Optional[str]:
    for cc in ("gcc", "clang"):
        if shutil.which(cc):
            return cc
    return None


class AssemblyDebugger:
    """
    Unified assembly debugger: disassembly + CFG + taint + symbolic execution.

    Graceful degradation:
      - Without capstone: returns empty report (tool_available=False)
      - Without angr: skips Phase 10, still runs Phases 8-9
      - Without a compiler: debug_source() returns empty report
    """

    def __init__(self, simgr_steps: int = 30):
        self._disasm = Disassembler()
        self._cfg_builder = CFGBuilder()
        self._cfg_analysis = CFGAnalysis()
        self._taint = TaintAnalyzer()
        self._angr = AngrAnalyzer(simgr_steps=simgr_steps)

    # ── public API ─────────────────────────────────────────────────────────────

    def debug_bytes(
        self,
        data: bytes,
        arch: str = "x86_64",
        base_addr: int = 0x1000,
        language: LanguageType = LanguageType.ASSEMBLY,
    ) -> UnifiedDebugReport:
        """
        Disassemble raw bytes, build CFG, run taint analysis.
        (Phase 10 / angr is skipped — no binary to load.)
        """
        report = UnifiedDebugReport(
            component=ComponentType.CPP_DEBUG,
            language=language,
            code=f"<{len(data)} bytes of {arch} machine code>",
        )

        if not capstone_available():
            report.risk_level = RiskLevel.LOW
            report.confidence_score = 0.0
            return report

        # Phase 8a: disassemble
        disasm_report = self._disasm.from_bytes(data, arch=arch, base_addr=base_addr)
        if disasm_report.error:
            return report

        # Phase 8b: CFG
        cfg = self._cfg_builder.build(disasm_report)
        cfg_patterns = self._cfg_analysis.analyse(cfg, language=language)

        # Phase 9: taint
        taint_findings = self._taint.analyse(cfg, disasm_report, language=language)
        taint_patterns = [f.to_bug_pattern(language) for f in taint_findings]

        all_patterns = cfg_patterns + taint_patterns
        report.patterns_detected = all_patterns
        _apply_risk(report, all_patterns)
        return report

    def debug_binary(
        self,
        path: str,
        arch: Optional[str] = None,
        language: LanguageType = LanguageType.ASSEMBLY,
    ) -> UnifiedDebugReport:
        """
        Disassemble + CFG + taint from a compiled ELF binary.
        Phase 10 (angr) also runs against the binary.
        """
        report = UnifiedDebugReport(
            component=ComponentType.CPP_DEBUG,
            language=language,
            code=f"<ELF binary: {path}>",
        )

        # Phase 8: disassembly
        disasm_report = self._disasm.from_binary(path, arch=arch)
        if not disasm_report.tool_available or disasm_report.error:
            report.risk_level = RiskLevel.LOW
            report.confidence_score = 0.0
            return report

        cfg = self._cfg_builder.build(disasm_report)
        cfg_patterns = self._cfg_analysis.analyse(cfg, language=language)

        # Phase 9: taint
        taint_findings = self._taint.analyse(cfg, disasm_report, language=language)
        taint_patterns = [f.to_bug_pattern(language) for f in taint_findings]

        # Phase 10: angr
        angr_report = self._angr.analyse_binary(path)
        angr_patterns = angr_report.to_bug_patterns(language=language) if angr_report.tool_available else []

        all_patterns = cfg_patterns + taint_patterns + angr_patterns
        report.patterns_detected = all_patterns
        _apply_risk(report, all_patterns)
        return report

    def debug_source(
        self,
        code: str,
        dialect: str = "c",
        language: LanguageType = LanguageType.ASSEMBLY,
    ) -> UnifiedDebugReport:
        """
        Compile C/C++ source, then run all three assembly phases.
        """
        report = UnifiedDebugReport(
            component=ComponentType.CPP_DEBUG,
            language=language,
            code=code,
        )

        cc = _c_compiler()
        if not cc or not capstone_available():
            report.risk_level = RiskLevel.LOW
            report.confidence_score = 0.0
            return report

        std = "-std=c++17" if dialect == "cpp" else "-std=c11"
        with tempfile.TemporaryDirectory() as tmpdir:
            suffix = ".cpp" if dialect == "cpp" else ".c"
            src = Path(tmpdir) / f"input{suffix}"
            binary = Path(tmpdir) / "input"
            src.write_text(code)
            try:
                res = subprocess.run(
                    [cc, std, "-g", "-O0", str(src), "-o", str(binary)],
                    capture_output=True, text=True, timeout=20,
                )
                if res.returncode != 0:
                    return report
            except Exception:
                return report

            return self.debug_binary(str(binary), language=language)


# ──────────────────────────────────────────────────────────────────────────────
# Risk classification helper
# ──────────────────────────────────────────────────────────────────────────────

def _apply_risk(report: UnifiedDebugReport, patterns: List[BugPattern]) -> None:
    if any(p.severity == BugSeverity.CRITICAL for p in patterns):
        report.risk_level = RiskLevel.CRITICAL
        report.confidence_score = 0.3
    elif any(p.severity == BugSeverity.HIGH for p in patterns):
        report.risk_level = RiskLevel.HIGH
        report.confidence_score = 0.6
    elif any(p.severity in (BugSeverity.MEDIUM, BugSeverity.LOW) for p in patterns):
        report.risk_level = RiskLevel.MEDIUM
        report.confidence_score = 0.8
    else:
        report.risk_level = RiskLevel.LOW
        report.confidence_score = 1.0
