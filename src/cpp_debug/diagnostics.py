"""
Clang compiler diagnostics: compiles C/C++ with -fsyntax-only -Wall -Wextra
and parses the resulting warnings/errors into structured records.

This is the fast, syntactic layer (analogous to rustc's borrow checker
diagnostics in rust_debug/borrow_checker.py). For deeper, path-sensitive
bugs (null derefs, memory leaks, dead stores), see analyzer.py which drives
the Clang Static Analyzer.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


def clang_available(dialect: str = "c") -> bool:
    """Check if the appropriate clang binary is on PATH."""
    binary = "clang++" if dialect == "cpp" else "clang"
    return shutil.which(binary) is not None


# Matches clang's standard diagnostic line:
#   /tmp/foo.c:3:12: warning: variable 'x' is uninitialized [-Wuninitialized]
#   /tmp/foo.c:7:8: error: use of undeclared identifier 'y'
_DIAG_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s+"
    r"(?P<severity>error|warning|note):\s+"
    r"(?P<message>.*?)"
    r"(?:\s+\[(?P<flag>-W[\w-]+|[\w.]+)\])?$"
)


class DiagnosticsCompiler:
    """Compiles C/C++ source with clang and extracts diagnostics."""

    DEFAULT_C_FLAGS = ["-fsyntax-only", "-Wall", "-Wextra", "-Wuninitialized",
                        "-Wsign-compare", "-Wformat=2", "-Wnull-dereference"]
    DEFAULT_CPP_FLAGS = DEFAULT_C_FLAGS + ["-std=c++17"]

    def __init__(self, timeout_seconds: int = 15):
        self.timeout_seconds = timeout_seconds

    def compile_and_diagnose(
        self,
        code: str,
        dialect: str = "c",
    ) -> Dict[str, Any]:
        """
        Compile `code` with clang/clang++ and return structured diagnostics.

        Returns:
            {
              "errors": [...], "warnings": [...], "notes": [...],
              "tool_available": bool, "raw_output": str
            }
        """
        binary = "clang++" if dialect == "cpp" else "clang"
        empty = {"errors": [], "warnings": [], "notes": [], "tool_available": False, "raw_output": ""}

        if not clang_available(dialect):
            return empty

        suffix = ".cpp" if dialect == "cpp" else ".c"
        flags = self.DEFAULT_CPP_FLAGS if dialect == "cpp" else self.DEFAULT_C_FLAGS

        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = subprocess.run(
                [binary, *flags, temp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            diagnostics = self._parse_diagnostics(result.stderr, temp_path)
            diagnostics["tool_available"] = True
            diagnostics["raw_output"] = result.stderr
            return diagnostics
        except subprocess.TimeoutExpired:
            return {**empty, "tool_available": True, "raw_output": "clang timed out"}
        except Exception as e:
            return {**empty, "tool_available": True, "raw_output": f"clang invocation failed: {e}"}
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _parse_diagnostics(self, stderr: str, temp_path: str) -> Dict[str, Any]:
        errors, warnings, notes = [], [], []
        for line in stderr.splitlines():
            m = _DIAG_RE.match(line.strip())
            if not m:
                continue
            entry = {
                "file": m.group("file"),
                "line": int(m.group("line")),
                "col": int(m.group("col")),
                "message": m.group("message").strip(),
                "flag": m.group("flag") or "",
            }
            severity = m.group("severity")
            if severity == "error":
                errors.append(entry)
            elif severity == "warning":
                warnings.append(entry)
            else:
                notes.append(entry)
        return {"errors": errors, "warnings": warnings, "notes": notes}
