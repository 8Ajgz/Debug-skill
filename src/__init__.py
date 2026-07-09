"""Verification-Debugging-Suite v2.6.1 - Production Ready

Unified verification and debugging orchestrator combining:
- PyProver v14.1 (formal verification with Z3, loop invariants, contract simplification)
- Python-Debug v12.3 (runtime debugging), now with working bandit + semgrep security static analysis in Phase 0 (v2.6.1)
- Test-Generator v1.1 (comprehensive test generation)
- Master-Debugger-v5 (4-phase orchestration, unified RiskLevel as of v2.6.1)
- Code-Orchestrator v1.1 (codebase analysis)
- Troubleshooting v1.0 (universal diagnostics)
- C/C++-Debug (Phase 4: Clang diagnostics + Static Analyzer + cppcheck second opinion + lief binary hardening)
- DWARF/Symbolic-Debug (Phases 5-6: DWARF binary analysis, CBMC/KLEE symbolic execution)
- C-Debug (Phase 7: strace syscall tracing + valgrind memcheck dynamic memory-error detection)
- Assembly-Debug (Phases 8-10: Capstone disassembly/CFG, taint dataflow, angr symbolic execution)
- Rust-Debug (Phases 2-3: borrow checker + clippy, now with honest tool-availability reporting)
"""

__version__ = "2.6.1"
__author__ = "Anthropic Claude"

# Core exports
from src.master_debugger.orchestrator_v5 import MasterDebuggerV5, RiskLevel, UnifiedReport
from src.python_debug.debug_report import execute_with_debug, DebugReport
from src.test_generator.test_generator import TestGenerator, generate_tests, TestCase, TestGenerationResult
from src.pyprover.contract_verifier import ContractVerifier, ContractSpec
from src.pyprover.async_verifier import AsyncVerifier
from src.pyprover.ffi_verifier import FFIVerifier
from src.pyprover.token_profiler import TokenProfiler
from src.troubleshooting.phases_5 import Troubleshooter
from src.code_orchestrator.orchestrator import CodeOrchestrator

# PyProver v14.1 additions (loop invariant verification + contract simplification)
from src.pyprover.loop_verifier import LoopVerifier, extract_loop_invariants, LoopVerificationReport
from src.pyprover.contract_simplifier import ContractSimplifier, simplify_parsed_contract, ContractSimplificationResult

# Cross-language bridge (routes bundled PyProver verification for non-Python languages)
from src.common.pyprover_bridge import PyProverBridge, PyProverResult, get_bridge, invoke_pyprover, detect_language

# C/C++-Debug (Phase 4-6): Clang diagnostics, DWARF analysis, CBMC/KLEE symbolic execution, cppcheck, lief
from src.cpp_debug.phases import CppDebugger
from src.cpp_debug.dwarf_analyzer import DWARFAnalyzer, DWARFReport, dwarf_available
from src.cpp_debug.symbolic_executor import SymbolicExecutor, SymbolicReport, cbmc_available, klee_available
from src.cpp_debug.cppcheck_analyzer import CppcheckAnalyzer, cppcheck_available
from src.cpp_debug.lief_analyzer import LiefBinaryAnalyzer, lief_available

# C-Debug (Phase 7): strace syscall tracing + valgrind memcheck, wraps CppDebugger
from src.c_debug.debugger import (
    CDebugger, SyscallTracer, SyscallReport, SyscallEvent, strace_available,
    ValgrindRunner, ValgrindReport, valgrind_available,
)

# Assembly-Debug (Phases 8-10): disassembly/CFG, taint dataflow, angr symbolic execution
from src.assembly_debug.phases import AssemblyDebugger
from src.assembly_debug.disassembler import Disassembler, DisassemblyReport, Arch, capstone_available
from src.assembly_debug.cfg import CFGBuilder, ControlFlowGraph, CFGAnalysis
from src.assembly_debug.dataflow import TaintAnalyzer, TaintFinding
from src.assembly_debug.symbolic import AngrAnalyzer, AngrReport, angr_available

# Rust-Debug (Phases 2-3): borrow checker + clippy
from src.rust_debug.phases import RustDebugger

__all__ = [
    # Master Debugger
    'MasterDebuggerV5',
    'RiskLevel',
    'UnifiedReport',
    # Python Debug
    'execute_with_debug',
    'DebugReport',
    # Test Generator
    'TestGenerator',
    'generate_tests',
    'TestCase',
    'TestGenerationResult',
    # PyProver
    'ContractVerifier',
    'ContractSpec',
    'AsyncVerifier',
    'FFIVerifier',
    'TokenProfiler',
    'LoopVerifier',
    'extract_loop_invariants',
    'LoopVerificationReport',
    'ContractSimplifier',
    'simplify_parsed_contract',
    'ContractSimplificationResult',
    # Troubleshooting
    'Troubleshooter',
    # Code Orchestrator
    'CodeOrchestrator',
    # Cross-language bridge
    'PyProverBridge',
    'PyProverResult',
    'get_bridge',
    'invoke_pyprover',
    'detect_language',
    # C/C++ Debug
    'CppDebugger',
    'DWARFAnalyzer',
    'DWARFReport',
    'dwarf_available',
    'SymbolicExecutor',
    'SymbolicReport',
    'cbmc_available',
    'klee_available',
    'CppcheckAnalyzer',
    'cppcheck_available',
    'LiefBinaryAnalyzer',
    'lief_available',
    # C Debug
    'CDebugger',
    'SyscallTracer',
    'SyscallReport',
    'SyscallEvent',
    'strace_available',
    'ValgrindRunner',
    'ValgrindReport',
    'valgrind_available',
    # Assembly Debug
    'AssemblyDebugger',
    'Disassembler',
    'DisassemblyReport',
    'Arch',
    'capstone_available',
    'CFGBuilder',
    'ControlFlowGraph',
    'CFGAnalysis',
    'TaintAnalyzer',
    'TaintFinding',
    'AngrAnalyzer',
    'AngrReport',
    'angr_available',
    # Rust Debug
    'RustDebugger',
]
