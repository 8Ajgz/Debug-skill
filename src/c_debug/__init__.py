"""
C-Debug (Phase 7) — C-specific debugger with strace syscall tracing and
valgrind memcheck.

Wraps CppDebugger (compiler diags + DWARF + symbolic) and adds runtime
observability via strace (syscall boundary bugs) and valgrind (dynamic
memory-error detection: leaks, invalid read/write, use-after-free,
uninitialised values). Provides a simpler, C-focused entry point with no
C++ template considerations.

Public API:
    CDebugger().debug(code)         -> UnifiedDebugReport
    CDebugger().static_only(code)   -> UnifiedDebugReport
    CDebugger().strace_only(code)   -> SyscallReport
    CDebugger().valgrind_only(code) -> ValgrindReport
    SyscallTracer().trace(code)     -> SyscallReport
    ValgrindRunner().run(code)      -> ValgrindReport
    strace_available()              -> bool
    valgrind_available()            -> bool
"""

from .debugger import (
    CDebugger,
    SyscallTracer,
    SyscallReport,
    SyscallEvent,
    ValgrindRunner,
    ValgrindReport,
    strace_available,
    valgrind_available,
    claude_check_and_install,
    REQUIRED_TOOLS,
    _parse_strace_output,
    _analyse_events,
    _parse_valgrind_output,
)

__version__ = "1.1.0"
__all__ = [
    "CDebugger",
    "SyscallTracer",
    "SyscallReport",
    "SyscallEvent",
    "ValgrindRunner",
    "ValgrindReport",
    "strace_available",
    "valgrind_available",
    "claude_check_and_install",
    "REQUIRED_TOOLS",
]
