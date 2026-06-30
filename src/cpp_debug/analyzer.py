"""
Clang Static Analyzer integration: drives `clang --analyze` for
path-sensitive bug detection (null dereferences, memory leaks,
use-after-free, dead stores, division by zero) that plain compiler
warnings cannot catch.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .diagnostics import _DIAG_RE, clang_available


class StaticAnalyzer:
    """Wraps the Clang Static Analyzer (`clang --analyze`)."""

    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    def analyze(self, code: str, dialect: str = "c") -> Dict[str, Any]:
        """
        Run the Clang Static Analyzer on `code`.

        Returns:
            {"findings": [...], "tool_available": bool, "raw_output": str}
        """
        binary = "clang++" if dialect == "cpp" else "clang"
        empty = {"findings": [], "tool_available": False, "raw_output": ""}

        if not clang_available(dialect):
            return empty

        suffix = ".cpp" if dialect == "cpp" else ".c"
        extra = ["-std=c++17"] if dialect == "cpp" else []

        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = subprocess.run(
                [binary, "--analyze", "-Xanalyzer", "-analyzer-output=text", *extra, temp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            findings = self._parse_findings(result.stderr)
            return {"findings": findings, "tool_available": True, "raw_output": result.stderr}
        except subprocess.TimeoutExpired:
            return {**empty, "tool_available": True, "raw_output": "clang --analyze timed out"}
        except Exception as e:
            return {**empty, "tool_available": True, "raw_output": f"clang --analyze failed: {e}"}
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _parse_findings(self, stderr: str) -> List[Dict[str, Any]]:
        """
        Parse top-level analyzer warnings (skip the 'note:' trail that
        explains the path the analyzer took to reach each finding -
        that trail is preserved in raw_output for anyone who wants it).
        """
        findings = []
        for line in stderr.splitlines():
            m = _DIAG_RE.match(line.strip())
            if not m or m.group("severity") != "warning":
                continue
            findings.append({
                "file": m.group("file"),
                "line": int(m.group("line")),
                "col": int(m.group("col")),
                "message": m.group("message").strip(),
                "checker": m.group("flag") or "",
            })
        return findings
