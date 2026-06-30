"""
Installation checker for C/C++-Debug (Phase 4).

Mirrors rust_debug/setup.py's claude_check_and_install() so MasterDebugger
can do the same uniform "check tools, warn if missing, continue anyway"
flow for every language-specific debugger.
"""
import shutil
import sys
from typing import Any, Dict

REQUIRED_TOOLS = {
    "clang": {
        "binary": "clang",
        "purpose": "C compiler diagnostics (-Wall -Wextra) + static analyzer",
        "install": {
            "apt": "apt-get install -y clang",
            "brew": "brew install llvm",
            "docs": "https://clang.llvm.org/get_started.html",
        },
    },
    "clang++": {
        "binary": "clang++",
        "purpose": "C++ compiler diagnostics + static analyzer",
        "install": {
            "apt": "apt-get install -y clang",
            "brew": "brew install llvm",
            "docs": "https://clang.llvm.org/get_started.html",
        },
    },
}


def _tool_available(binary: str) -> bool:
    return shutil.which(binary) is not None


def claude_check_and_install() -> Dict[str, Any]:
    """
    Check whether clang/clang++ are available. If not, print install
    instructions to stderr (does not block - debug-suite continues with
    degraded C/C++ analysis, same as the Rust toolchain check).

    Returns:
        {"clang_available": bool, "clangpp_available": bool, "all_available": bool}
    """
    clang_ok = _tool_available("clang")
    clangpp_ok = _tool_available("clang++")
    status = {
        "clang_available": clang_ok,
        "clangpp_available": clangpp_ok,
        "all_available": clang_ok and clangpp_ok,
    }

    if not status["all_available"]:
        print("\n" + "=" * 80, file=sys.stderr)
        print("CPP-DEBUG SETUP REQUIRED", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        if not clang_ok:
            print("❌ clang not found. Install: apt-get install -y clang", file=sys.stderr)
        if not clangpp_ok:
            print("❌ clang++ not found. Install: apt-get install -y clang", file=sys.stderr)
        print("(macOS: brew install llvm)", file=sys.stderr)
        print("=" * 80 + "\n", file=sys.stderr)

    return status
