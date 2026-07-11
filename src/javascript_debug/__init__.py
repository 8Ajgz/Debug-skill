"""
JavaScript Debug v1.0 - Part of Verification-Debugging-Suite

Execute JavaScript code with full execution visibility and detect common bug patterns.
Integrates runtime variable tracking, Promise/async tracking, aliasing detection, and
automatic bug pattern recognition for Node.js and browser environments.

Core API:
- execute_with_debug(code, globalScope, options) -> ExecutionReport
- BugPatternDetector(report) -> List[DetectedPattern]
- Detects: NULL_REFERENCE, TYPE_MISMATCH, OFF_BY_ONE, ALIASING_MUTATION,
  UNHANDLED_PROMISE, RACE_CONDITION, CLOSURE_CAPTURE, PROTOTYPE_POLLUTION,
  MEMORY_LEAK, FLOATING_POINT

Compatibility: Node.js 14+ or ES2020+ browsers (zero external dependencies)
"""

import json
import os
import shutil
import subprocess
import tempfile

__version__ = "1.0.0"
__author__ = "Verification-Debugging-Suite Contributors"

# When used in suite, JS debugging is invoked via subprocess/Node.js
# The Python API is minimal; the heavy lifting is in JavaScript
# This module handles orchestration and result parsing

_RUNNER_PATH = os.path.join(os.path.dirname(__file__), "_runner.js")


class JavaScriptDebugger:
    """
    Orchestrates JavaScript debugging via Node.js subprocess.
    Handles code execution, result parsing, and pattern detection.
    """
    
    def __init__(self):
        self.debug_engine_path = os.path.join(os.path.dirname(__file__), "debug-engine.js")
        self.node_available = shutil.which("node") is not None
        self.supported_patterns = [
            "NULL_REFERENCE",
            "TYPE_MISMATCH", 
            "OFF_BY_ONE",
            "ALIASING_MUTATION",
            "UNHANDLED_PROMISE",
            "RACE_CONDITION",
            "CLOSURE_CAPTURE",
            "PROTOTYPE_POLLUTION",
            "MEMORY_LEAK",
            "FLOATING_POINT"
        ]
    
    def execute_with_debug(self, code: str, global_scope: dict = None, options: dict = None):
        """
        Execute JavaScript with full execution visibility.
        
        Args:
            code (str): JavaScript code to execute
            global_scope (dict, optional): Variables/functions available in code
            options (dict, optional): { traceVariables: True, timeout: 5000 }
        
        Returns:
            dict with keys:
              - success (bool)
              - report (dict): debug-engine.js's DebugReport.toJSON() —
                timeline, variables, promises, asyncEvents, exceptionInfo
              - patterns (list[dict]): bug patterns already detected by
                bug-patterns.js's BugPatternDetector, computed in the same
                Node subprocess (see analyze_patterns() docstring for why
                this can't be deferred to a separate later call)
              - error (str, only present when success is False)

        Replaces the previous stub (a bare `pass`, returning None
        regardless of input — see STUBS.md). Degrades honestly if Node.js
        isn't installed, matching the tool-availability convention used
        elsewhere in this suite (rust_debug/cpp_debug).
        """
        if not self.node_available:
            return {
                "success": False,
                "error": "node is not installed — JavaScript execution was not performed",
            }

        timeout_sec = max(5, ((options or {}).get("timeout", 5000) / 1000) + 2)
        with tempfile.TemporaryDirectory() as tmpdir:
            code_path = os.path.join(tmpdir, "code.js")
            with open(code_path, "w") as f:
                f.write(code)

            args = ["node", _RUNNER_PATH, code_path]
            if global_scope is not None or options is not None:
                args.append(json.dumps(global_scope or {}))
            if options is not None:
                args.append(json.dumps(options))

            try:
                proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                return {"success": False, "error": f"execution timed out after {timeout_sec}s"}

            try:
                result = json.loads(proc.stdout)
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "error": "runner produced non-JSON output",
                    "raw_stdout": proc.stdout[-2000:],
                    "raw_stderr": proc.stderr[-2000:],
                }
            return result
    
    def analyze_patterns(self, report):
        """Detect bug patterns in an execution report.

        `report` is expected to be the dict returned by
        `execute_with_debug()` (or one already containing a "patterns"
        key in that same shape). Pattern detection can't be run as a
        genuinely separate, later step from execution: bug-patterns.js's
        BugPatternDetector reads the live JS DebugReport as a Map plus
        calls methods like getTrueAliases()/getVariableMutations(),
        none of which survive the JSON round-trip back to Python — so
        `execute_with_debug()` already runs pattern detection inside the
        same Node subprocess and this method just re-exposes that result.
        This replaces the previous stub (a bare `pass`, returning None
        regardless of input — see STUBS.md).
        """
        if isinstance(report, dict) and "patterns" in report:
            return report["patterns"]
        return []


__all__ = [
    "JavaScriptDebugger",
    "__version__",
]
