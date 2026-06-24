"""
Verification-Debugging-Suite v1.0

Unified suite for code verification, debugging, testing, and problem diagnosis.

Quick Start:
    from verification_debugging_suite import MasterDebuggerV5
    
    debugger = MasterDebuggerV5()
    report = debugger.debug(code)
    print(report.summary)
"""

__version__ = "1.0.0"
__author__ = "Anthropic"

# Import main components
try:
    from src.master_debugger import MasterDebuggerV5, RiskLevel, UnifiedReport
except ImportError:
    # Fallback for different import paths
    try:
        from master_debugger import MasterDebuggerV5, RiskLevel, UnifiedReport
    except ImportError:
        pass

try:
    from src.python_debug import execute_with_debug
except ImportError:
    try:
        from python_debug import execute_with_debug
    except ImportError:
        pass

try:
    from src.troubleshooting import Troubleshooter
except ImportError:
    try:
        from troubleshooting import Troubleshooter
    except ImportError:
        pass

try:
    from src.pyprover import ContractVerifier
except ImportError:
    try:
        from pyprover import ContractVerifier
    except ImportError:
        pass

try:
    from src.test_generator import TestGenerator
except ImportError:
    try:
        from test_generator import TestGenerator
    except ImportError:
        pass

try:
    from src.code_orchestrator import CodeOrchestrator
except ImportError:
    try:
        from code_orchestrator import CodeOrchestrator
    except ImportError:
        pass

__all__ = [
    'MasterDebuggerV5',
    'RiskLevel',
    'UnifiedReport',
    'execute_with_debug',
    'Troubleshooter',
    'ContractVerifier',
    'TestGenerator',
    'CodeOrchestrator',
]
