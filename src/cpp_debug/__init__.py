"""
C/C++-Debug (Phase 4) - Debug-Suite v2.6.1

Static analysis for C and C++ using Clang's compiler diagnostics, the
Clang Static Analyzer (path-sensitive symbolic checking), cppcheck
(dataflow-based second opinion), and lief (compiled-binary hardening
posture + dangerous-import detection).

This is the production implementation of roadmap Phase 4 ("C/C++ AST Parser").
Design note: rather than walking Clang's raw AST in Python (the originally
sketched approach), this implementation drives `clang -fsyntax-only` and
`clang --analyze` directly and parses their structured diagnostic output.
This gives the same bug-pattern coverage (uninitialized variables, null
dereferences, type mismatches, memory issues, dead stores) with far less
code and no dependency on libclang Python bindings, which are not reliably
available in sandboxed environments. Diagnostic-based detection is also
what Clang-Tidy and scan-build use in production, so it is a well-trodden
path rather than a shortcut. cppcheck (v2.6.0+) runs alongside Clang as a
second, independently-implemented static analyzer to catch what CSA misses.
lief (v2.6.1+) checks the *compiled binary* rather than source - PIE/NX/
RELRO/stack-canary hardening flags and dangerous imports (system, strcpy,
gets, ...) straight from the import table, a capability none of the
source-level analyzers have.

Public API:
    CppDebugger().debug(code, dialect="c"|"cpp") -> UnifiedDebugReport
"""

from .phases import CppDebugger
from .setup import claude_check_and_install, REQUIRED_TOOLS
from .dwarf_analyzer import DWARFAnalyzer, DWARFReport, dwarf_available
from .symbolic_executor import SymbolicExecutor, SymbolicReport, cbmc_available, klee_available
from .cppcheck_analyzer import CppcheckAnalyzer, cppcheck_available
from .lief_analyzer import LiefBinaryAnalyzer, lief_available

__version__ = "1.4.0"
__all__ = [
    "CppDebugger", "claude_check_and_install", "REQUIRED_TOOLS",
    "DWARFAnalyzer", "DWARFReport", "dwarf_available",
    "SymbolicExecutor", "SymbolicReport", "cbmc_available", "klee_available",
    "CppcheckAnalyzer", "cppcheck_available",
    "LiefBinaryAnalyzer", "lief_available",
]
