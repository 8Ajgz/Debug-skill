"""Troubleshooting diagnostics implementation.

Previously three classes here (UniversalTroubleshooter, ToolDiagnostician,
HealthChecker) were stubs that always returned the same canned result
regardless of input, AND were unreachable dead code — nothing in the
suite imported this module directly, only `troubleshooting/phases_5.py`'s
separate, more complete `Troubleshooter`/`DiagnosisResult` (see
troubleshooting/__init__.py). That combination (fake results + reachable
via a direct import path) was flagged in STUBS.md as dangerous rather than
merely incomplete: anyone importing this module directly, rather than via
`__init__.py`, got fake results with no signal that they were fake.

Decision recorded here (per the handoff's Continue-From-Here item 3):
implement these for real rather than deleting them. Unlike
`phases_5.py`'s `Troubleshooter` (diagnoses one described symptom via the
6-phase methodology), `HealthChecker` covers different, genuinely useful
ground -- a real cross-suite tool-availability check -- that nothing else
in the suite currently aggregates in one place. `UniversalTroubleshooter`
and `ToolDiagnostician` are now real, input-dependent implementations
rather than deletion candidates, and are exported from `__init__.py` so
they're reachable through the supported path instead of being dead code
reachable only through a direct, undocumented import.
"""
import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
from enum import Enum


class TroubleshootingPhase(str, Enum):
    EVIDENCE = "evidence"
    CLASSIFICATION = "classification"
    DISCOVERY = "discovery"
    FIXES = "fixes"
    VALIDATION = "validation"


@dataclass
class DiagnosisReport:
    phase: TroubleshootingPhase
    root_cause: str
    confidence: float
    auto_fixable: bool
    suggestions: List[str]
    details: Dict[str, Any]


class UniversalTroubleshooter:
    """Universal troubleshooting for any tool failure."""

    async def diagnose_problem(
        self,
        symptom: str,
        context: Optional[Dict[str, Any]] = None,
        tool: str = "unknown"
    ) -> Union[DiagnosisReport, Exception]:
        context = context or {}
        evidence = {"symptom": symptom, "tool": tool, "context": context}
        classification = self._classify_problem(evidence)
        actual_state = {"classification": classification}
        fixes = self._suggest_fixes(actual_state, tool)
        best_fix = max(fixes, key=lambda f: f.get("confidence", 0)) if fixes else {}

        return DiagnosisReport(
            phase=TroubleshootingPhase.VALIDATION,
            root_cause=best_fix.get("cause", "Unknown"),
            confidence=best_fix.get("confidence", 0.5),
            auto_fixable=best_fix.get("auto_fixable", False),
            suggestions=best_fix.get("suggestions", []),
            details={"evidence": evidence, "classification": classification, "tool": tool}
        )

    def _classify_problem(self, evidence: Dict[str, Any]) -> str:
        symptom = evidence.get("symptom", "").lower()
        if "not found" in symptom or "no such file" in symptom or "command not found" in symptom:
            return "missing_dependency"
        if "permission" in symptom or "access denied" in symptom or "eacces" in symptom:
            return "permission_error"
        if "parse" in symptom or "syntax" in symptom or "unexpected token" in symptom:
            return "input_error"
        if "timeout" in symptom or "timed out" in symptom or "hang" in symptom:
            return "performance_error"
        if "memory" in symptom or "oom" in symptom or "out of memory" in symptom:
            return "resource_error"
        if "import" in symptom or "module" in symptom and "not found" not in symptom:
            return "import_error"
        return "runtime_error"

    def _suggest_fixes(self, state: Dict[str, Any], tool: str) -> List[Dict[str, Any]]:
        """Real, classification-dependent suggestions.

        Previously this ignored `state` entirely and always returned the
        identical {"cause": "Unknown error", ..., "confidence": 0.7} —
        see STUBS.md. Each branch below now reflects the actual
        classification produced by `_classify_problem`.
        """
        classification = state.get("classification", "runtime_error")

        if classification == "missing_dependency":
            return [{
                "cause": f"{tool} (or a binary/package it depends on) is not installed",
                "suggestions": [
                    f"Check whether {tool}'s required binary is on PATH (shutil.which)",
                    "See this component's setup.py for the exact install command",
                ],
                "auto_fixable": True,
                "confidence": 0.85,
            }]
        if classification == "permission_error":
            return [{
                "cause": f"{tool} lacks permission to access a required file or resource",
                "suggestions": [
                    "Check file/directory permissions for the path involved",
                    "Re-run with appropriate privileges, or fix ownership rather than "
                    "escalating privileges",
                ],
                "auto_fixable": False,
                "confidence": 0.75,
            }]
        if classification == "input_error":
            return [{
                "cause": f"{tool} was given input it could not parse",
                "suggestions": [
                    "Check the input against this component's documented supported syntax",
                    "Look for unclosed delimiters, unsupported language constructs, "
                    "or encoding issues",
                ],
                "auto_fixable": False,
                "confidence": 0.8,
            }]
        if classification == "performance_error":
            return [{
                "cause": f"{tool} exceeded its time budget",
                "suggestions": [
                    "Check for unbounded loops/recursion or pathological input size",
                    "Increase the component's timeout if the workload is legitimately large",
                ],
                "auto_fixable": False,
                "confidence": 0.7,
            }]
        if classification == "resource_error":
            return [{
                "cause": f"{tool} exhausted available memory or another finite resource",
                "suggestions": [
                    "Check input size and any exponential-blowup code paths "
                    "(e.g. unbounded Z3 search, deep recursion)",
                    "Run with a smaller input to confirm the resource ceiling",
                ],
                "auto_fixable": False,
                "confidence": 0.65,
            }]
        if classification == "import_error":
            return [{
                "cause": f"{tool} depends on a Python package that isn't installed",
                "suggestions": [
                    "pip install the missing package with --break-system-packages "
                    "in this environment",
                    "Check requirements.txt for the expected version",
                ],
                "auto_fixable": True,
                "confidence": 0.8,
            }]
        return [{
            "cause": f"{tool} failed for an unclassified reason",
            "suggestions": [
                f"Check {tool}'s logs/stderr for the underlying exception",
                "Re-run with verbose/debug output enabled if available",
            ],
            "auto_fixable": False,
            "confidence": 0.4,
        }]


class ToolDiagnostician:
    async def diagnose_pyprover_failure(self, error: Exception, code: Optional[str] = None) -> Dict[str, Any]:
        """Real, exception-dependent diagnosis.

        Previously this always returned
        {"suggestions": ["Simplify code"]} regardless of the actual
        exception (see STUBS.md). Now inspects the exception type/message
        (and, where relevant, the code) to give a targeted suggestion.
        """
        err_type = type(error).__name__
        msg = str(error).lower()

        if isinstance(error, NotImplementedError) or "notimplementederror" in err_type.lower():
            return {
                "tool": "pyprover",
                "cause": f"Unsupported syntax: {error}",
                "suggestions": [
                    "This AST construct is outside pyprover's documented supported "
                    "subset (see contract_verifier.py/loop_verifier.py docstrings)",
                    "Rewrite the contract/expression using only supported operators",
                ],
            }
        if "z3" in msg and ("not found" in msg or "no module" in msg or "import" in msg):
            return {
                "tool": "pyprover",
                "cause": "z3-solver is not installed",
                "suggestions": ["pip install z3-solver --break-system-packages"],
            }
        if isinstance(error, TimeoutError) or "timeout" in msg:
            return {
                "tool": "pyprover",
                "cause": "Z3 solver timed out",
                "suggestions": [
                    "Simplify the contract (fewer quantifiers/nested conditions)",
                    "Increase the solver timeout if the property is legitimately complex",
                ],
            }
        if isinstance(error, SyntaxError) or "syntax" in msg:
            location = ""
            if code:
                location = " — check '// Pre:'/'// Post:' or '# Pre:'/'# Post:' annotation syntax"
            return {
                "tool": "pyprover",
                "cause": f"Contract annotation could not be parsed: {error}",
                "suggestions": [f"Check the contract syntax in the source{location}"],
            }
        return {
            "tool": "pyprover",
            "cause": f"{err_type}: {error}",
            "suggestions": [
                "No specific pattern matched this exception type; check the full "
                "traceback for the failing verification step",
            ],
        }


# Real per-tool availability probes reused by HealthChecker. Each returns
# (installed: bool, detail: str). These mirror the same shutil.which /
# subprocess convention already used per-component elsewhere in this
# suite (rust_debug/borrow_checker.py, cpp_debug/setup.py, etc.) rather
# than introducing a new one.
def _probe_binary(name: str, version_flag: str = "--version") -> "tuple[bool, str]":
    path = shutil.which(name)
    if path is None:
        return False, f"{name} not found on PATH"
    try:
        subprocess.run([name, version_flag], capture_output=True, timeout=5)
        return True, path
    except Exception as e:
        return False, f"{name} found at {path} but failed to run: {e}"


def _probe_python_package(module_name: str) -> "tuple[bool, str]":
    import importlib.util
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return False, f"Python package '{module_name}' is not installed"
    return True, f"Python package '{module_name}' is installed"


class HealthChecker:
    async def check_all_tools(self) -> Dict[str, Dict[str, Any]]:
        """Real per-component health check.

        Previously this was hardcoded to report every component as
        "healthy" unconditionally, structurally incapable of ever
        reporting a real problem (see STUBS.md). Now actually probes
        each component's real external dependencies via shutil.which/
        subprocess/importlib, the same way each component checks its own
        tool availability internally (rust_debug._check_rustc,
        cpp_debug.setup.check_tool, etc.) — this just aggregates those
        checks in one place, which nothing else in the suite currently
        does.
        """
        results: Dict[str, Dict[str, Any]] = {}

        z3_ok, z3_detail = _probe_python_package("z3")
        hyp_ok, hyp_detail = _probe_python_package("hypothesis")
        results["pyprover"] = {
            "status": "healthy" if z3_ok else "degraded",
            "details": {"z3-solver": z3_detail, "hypothesis": hyp_detail},
        }

        results["python_debug"] = {"status": "healthy", "details": "pure-Python, no external tool dependency"}

        pytest_ok, pytest_detail = _probe_python_package("pytest")
        cov_ok, cov_detail = _probe_python_package("coverage")
        jest_ok, jest_detail = _probe_binary("jest")
        results["test_generator"] = {
            "status": "healthy" if (pytest_ok and cov_ok) else "degraded",
            "details": {"pytest": pytest_detail, "coverage.py": cov_detail, "jest": jest_detail},
        }

        results["code_orchestrator"] = {"status": "healthy", "details": "pure-Python, no external tool dependency"}
        results["troubleshooting"] = {"status": "healthy", "details": "pure-Python, no external tool dependency"}

        rustc_ok, rustc_detail = _probe_binary("rustc")
        clippy_ok, clippy_detail = _probe_binary("cargo-clippy", "--help")
        clang_ok, clang_detail = _probe_binary("clang")
        results["master_debugger"] = {
            "status": "healthy" if (rustc_ok and clang_ok) else "degraded",
            "details": {
                "rustc": rustc_detail, "clippy": clippy_detail, "clang": clang_detail,
                "note": "master_debugger degrades gracefully per-language when a "
                        "toolchain is missing rather than failing outright",
            },
        }

        return results


troubleshooter = UniversalTroubleshooter()
diagnostician = ToolDiagnostician()
health_checker = HealthChecker()


async def diagnose_problem(symptom: str, context: Optional[Dict[str, Any]] = None, tool: str = "unknown") -> Union[DiagnosisReport, Exception]:
    return await troubleshooter.diagnose_problem(symptom, context, tool)


async def check_tool_health(tool: str) -> Dict[str, Any]:
    health = await health_checker.check_all_tools()
    return health.get(tool, {"status": "unknown"})
