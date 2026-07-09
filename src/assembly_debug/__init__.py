"""
Assembly Debug (Phases 8-10) — Debug Suite v2.5

Phase 8: Capstone-based disassembly + Control Flow Graph construction
Phase 9: Register dataflow taint analysis over the CFG
Phase 10: angr symbolic execution for crash/vulnerability detection

Public API:
    AssemblyDebugger().debug_bytes(data, arch, base_addr) → UnifiedDebugReport
    AssemblyDebugger().debug_binary(path)                 → UnifiedDebugReport
    AssemblyDebugger().debug_source(code, dialect)        → UnifiedDebugReport
    Disassembler().from_bytes(data, arch, base_addr)      → DisassemblyReport
    CFGBuilder().build(disasm_report)                     → ControlFlowGraph
    TaintAnalyzer().analyse(cfg)                          → List[TaintFinding]
    AngrAnalyzer().analyse_binary(path)                   → AngrReport
"""

from .disassembler import (
    AsmInstruction, DisassemblyReport, Disassembler, Arch,
    capstone_available, disasm_check_and_install, REQUIRED_TOOLS as DISASM_TOOLS,
)
from .cfg import (
    BasicBlock, CFGEdge, ControlFlowGraph, CFGBuilder, CFGAnalysis,
)
from .dataflow import (
    DataflowState, TaintFinding, TaintAnalyzer,
)
from .symbolic import (
    AngrReport, FunctionSummary, CrashReport, AngrAnalyzer,
    angr_available, angr_check_and_install, REQUIRED_TOOLS as ANGR_TOOLS,
)
from .phases import AssemblyDebugger

__version__ = "1.0.0"
__all__ = [
    # Phase 8
    "AsmInstruction", "DisassemblyReport", "Disassembler", "Arch",
    "capstone_available", "disasm_check_and_install",
    "BasicBlock", "CFGEdge", "ControlFlowGraph", "CFGBuilder", "CFGAnalysis",
    # Phase 9
    "DataflowState", "TaintFinding", "TaintAnalyzer",
    # Phase 10
    "AngrReport", "FunctionSummary", "CrashReport", "AngrAnalyzer",
    "angr_available", "angr_check_and_install",
    # Unified facade
    "AssemblyDebugger",
]
