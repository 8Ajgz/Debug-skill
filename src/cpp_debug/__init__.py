"""
C/C++-Debug (Phase 4) - Debug-Suite v2.2

Static analysis for C and C++ using Clang's compiler diagnostics and the
Clang Static Analyzer (path-sensitive symbolic checking).

This is the production implementation of roadmap Phase 4 ("C/C++ AST Parser").
Design note: rather than walking Clang's raw AST in Python (the originally
sketched approach), this implementation drives `clang -fsyntax-only` and
`clang --analyze` directly and parses their structured diagnostic output.
This gives the same bug-pattern coverage (uninitialized variables, null
dereferences, type mismatches, memory issues, dead stores) with far less
code and no dependency on libclang Python bindings, which are not reliably
available in sandboxed environments. Diagnostic-based detection is also
what Clang-Tidy and scan-build use in production, so it is a well-trodden
path rather than a shortcut.

Public API:
    CppDebugger().debug(code, dialect="c"|"cpp") -> UnifiedDebugReport
"""

from .phases import CppDebugger
from .setup import claude_check_and_install, REQUIRED_TOOLS

__version__ = "1.0.0"
__all__ = ["CppDebugger", "claude_check_and_install", "REQUIRED_TOOLS"]
