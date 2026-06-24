"""Verification-Debugging-Suite v1.0.0 - Production Ready

Unified verification and debugging orchestrator combining:
- PyProver v14.0 (formal verification with Z3)
- Python-Debug v12.3 (runtime debugging)
- Test-Generator v1.1 (comprehensive test generation)
- Master-Debugger-v5 (4-phase orchestration)
- Code-Orchestrator v1.1 (codebase analysis)
- Troubleshooting v1.0 (universal diagnostics)
"""

__version__ = "1.0.0"
__author__ = "Anthropic Claude"

# Core exports
from src.master_debugger.orchestrator_v5 import MasterDebuggerV5, RiskLevel, UnifiedReport
from src.python_debug.debug_report import execute_with_debug, DebugReport
from src.test_generator import TestGenerator, generate_tests, TestCase, TestGenerationResult
from src.pyprover.contract_verifier import ContractVerifier, ContractSpec
from src.pyprover.async_verifier import AsyncVerifier
from src.pyprover.ffi_verifier import FFIVerifier
from src.pyprover.token_profiler import TokenProfiler
from src.troubleshooting.phases_5 import Troubleshooter
from src.code_orchestrator.orchestrator import CodeOrchestrator

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
    # Troubleshooting
    'Troubleshooter',
    # Code Orchestrator
    'CodeOrchestrator',
]
