"""
Rust-Debug Module (Phases 2-3)

Components:
  - Phase 2: Borrow Checker Parser (borrow_checker.py)
  - Phase 3: Clippy Linter Integration (clippy_linter.py)
  - Unified Debugger (phases.py)
  - Setup/Installation (setup.py)

Main entry point: RustDebugger class

Example:
    from src.rust_debug import RustDebugger
    debugger = RustDebugger()
    report = debugger.debug(rust_code)
"""

from .phases import RustDebugger
from .setup import claude_check_and_install, print_setup_guide, REQUIRED_TOOLS

__all__ = [
    "RustDebugger",
    "claude_check_and_install",
    "print_setup_guide",
    "REQUIRED_TOOLS",
]

__version__ = "2.0.0"
__phases__ = ["2", "3"]
