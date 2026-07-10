"""Master Debugger - Automated debugging orchestrator.

Active orchestrator: MasterDebugger (v6, src/master_debugger/orchestrator.py)
  - supports all languages including Assembly, C, C++, Rust
  - async debug_comprehensive() → UnifiedDebugReport

Legacy compat: MasterDebuggerV5 (src/master_debugger/orchestrator_v5.py)
  - sync debug() → UnifiedReport (Python/JS only)
  - retained for backward compatibility
"""
from .orchestrator import MasterDebugger          # v6 — active orchestrator
from .orchestrator_v5 import MasterDebuggerV5     # v5 — legacy compat
from .types import RiskLevel, UnifiedReport

__version__ = "6.0.0"
__all__ = ['MasterDebugger', 'MasterDebuggerV5', 'RiskLevel', 'UnifiedReport']
