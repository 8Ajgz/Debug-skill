"""Master-Debugger v6 4-phase orchestration with PyProver integration.

Phases:
  0: Static analysis (type checks, linters, AST inspection)
  1: Runtime debugging (execution tracing, pattern detection)
  2: Formal verification (Z3 + PyProver for 12 languages)
  3: Design review (architecture, design patterns, best practices)
"""
import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum

# Import PyProver bridge
try:
    from ..common.pyprover_bridge import PyProverBridge, invoke_pyprover
except ImportError:
    PyProverBridge = None
    invoke_pyprover = None

# Import Rust debugger (Phases 2-3)
try:
    from ..rust_debug import RustDebugger, claude_check_and_install
except ImportError:
    RustDebugger = None
    claude_check_and_install = None

# Import C/C++ debugger (Phase 4)
try:
    from ..cpp_debug import CppDebugger, claude_check_and_install as cpp_check_and_install
except ImportError:
    CppDebugger = None
    cpp_check_and_install = None

# RiskLevel used to be redefined here too (a third duplicate, alongside
# master_debugger.types.RiskLevel and common.interop.RiskLevel - see
# roadmap.md §11.6). This module (MasterDebugger, not MasterDebuggerV5) is
# not imported anywhere else in src/ or tests/ as of v2.6.0, so this had no
# live behavioral effect, but fixed for consistency now that the other two
# are unified onto common.interop.RiskLevel.
from ..common.interop import RiskLevel


class DebugPhase(str, Enum):
    STATIC = "static"
    RUNTIME = "runtime"
    FORMAL = "formal"
    TESTING = "testing"


@dataclass
class Issue:
    phase: DebugPhase
    type: str
    description: str
    severity: str
    location: Optional[str] = None
    fix: Optional[str] = None
    confidence: float = 0.8


@dataclass
class UnifiedDebugReport:
    phases_completed: List[DebugPhase] = field(default_factory=list)
    issues_found: List[Issue] = field(default_factory=list)
    test_suite: str = ""
    overall_health: str = "unknown"
    token_cost: int = 0
    recommendations: List[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    confidence_score: float = 0.0
    pyprover_result: Optional[Dict[str, Any]] = None
    # Set when phase 5 (regression test generation) fails. Phase 5 is
    # non-fatal, so the report is still returned, but the failure must not
    # look like "no tests were needed".
    test_generation_error: Optional[str] = None


class MasterDebugger:
    """
    Master-Debugger v6: 4-phase code analysis orchestrator.
    
    Automatically routes through phases based on risk classification.
    Integrates with PyProver for formal verification across 12 languages.
    """
    
    def __init__(self, use_pyprover: bool = True):
        """
        Initialize Master-Debugger.
        
        Args:
            use_pyprover: Enable PyProver integration for formal verification
        """
        self.use_pyprover = use_pyprover
        self.pyprover_bridge = None
        self.rust_debugger = None
        
        if use_pyprover and PyProverBridge is not None:
            self.pyprover_bridge = PyProverBridge(use_pyprover=True)
        
        if RustDebugger is not None:
            self.rust_debugger = RustDebugger()
            # Check if rustc/clippy are available; warn Claude if not
            if claude_check_and_install:
                status = claude_check_and_install()
                if not status.get("all_available"):
                    print(
                        "[MasterDebugger] ⚠️  Rust tools not fully installed. "
                        "Run: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
                        file=sys.stderr,
                    )
        
        self.cpp_debugger = None
        if CppDebugger is not None:
            self.cpp_debugger = CppDebugger()
            if cpp_check_and_install:
                status = cpp_check_and_install()
                if not status.get("all_available"):
                    print(
                        "[MasterDebugger] ⚠️  Clang tools not fully installed. "
                        "Run: apt-get install -y clang",
                        file=sys.stderr,
                    )
    
    async def debug_comprehensive(
        self,
        code: str,
        language: str = "python",
        input_data: Optional[Dict[str, Any]] = None,
        phases: Optional[List[str]] = None,
        timeout: int = 120,
    ) -> Union[UnifiedDebugReport, Exception]:
        """
        Comprehensive code debugging through all phases.
        
        Args:
            code: Source code to analyze
            language: Programming language (python, rust, cpp, etc.)
            input_data: Test input data for runtime phase
            phases: Which phases to run (default: all)
            timeout: Max seconds to spend
        
        Returns:
            UnifiedDebugReport with findings across all phases
        """
        if phases is None:
            phases = ["static", "runtime", "formal", "testing"]
        
        # Route to language-specific debugger if available
        if language.lower() == "rust" and self.rust_debugger is not None:
            return self.rust_debugger.debug(code)
        # Assembly: route to AssemblyDebugger (Phases 8-10)
        if language.lower() in ("assembly", "asm", "nasm", "fasm", "x86", "x86_64", "arm", "arm64"):
            try:
                from ..assembly_debug import AssemblyDebugger
                arch_map = {
                    "x86_64": "x86_64", "x86": "x86_32", "asm": "x86_64",
                    "assembly": "x86_64", "nasm": "x86_64", "fasm": "x86_64",
                    "arm": "arm", "arm64": "arm64",
                }
                arch = arch_map.get(language.lower(), "x86_64")
                # Treat code as raw bytes if hex-decodable, else disassemble as source
                try:
                    raw = bytes.fromhex(code.replace(" ", "").replace("\n", ""))
                    return AssemblyDebugger().debug_bytes(raw, arch=arch)
                except ValueError:
                    return AssemblyDebugger().debug_source(code, dialect="c")
            except Exception:
                pass  # Fall through to generic path
        # Plain C: route to CDebugger (adds strace syscall tracing on top of CppDebugger)
        if language.lower() == "c":
            try:
                from ..c_debug import CDebugger
                return CDebugger().debug(code)
            except Exception:
                pass  # Fall through to CppDebugger if c_debug unavailable
        if language.lower() in ("c", "cpp", "c++") and self.cpp_debugger is not None:
            dialect = "cpp" if language.lower() in ("cpp", "c++") else "c"
            return self.cpp_debugger.debug(code, dialect=dialect)
        
        report = UnifiedDebugReport()
        token_cost = 0

        # Phase 0 + 1 + 3: for Python, delegate to the real static/runtime/design
        # analyzers (mypy + python-debug execution tracing) instead of stubbing.
        # Other languages fall back to PyProver-only formal verification (Phase 2)
        # until a language-specific static/runtime analyzer is added.
        if language.lower() == "python":
            try:
                from .phases import (
                    Phase0StaticAnalysis,
                    Phase1RuntimeDebug,
                    Phase3DesignReview,
                )
                if "static" in phases:
                    static_result = Phase0StaticAnalysis.run(code)
                    # Real bug fixed here (see roadmap.md §20): these findings
                    # used to be counted into a local int and then discarded --
                    # report.issues_found never received them, so the final
                    # synthesis below (which reads report.issues_found) was
                    # structurally blind to every static finding. Now appended
                    # as real Issue objects so they actually participate.
                    for err in static_result.mypy_errors:
                        report.issues_found.append(Issue(
                            phase=DebugPhase.STATIC, type="mypy_error",
                            description=err, severity="medium", confidence=0.9,
                        ))
                    for issue in static_result.pylint_issues:
                        report.issues_found.append(Issue(
                            phase=DebugPhase.STATIC, type="pylint_issue",
                            description=issue, severity="low", confidence=0.7,
                        ))
                    # bandit and semgrep findings were computed into the result
                    # but never copied here, so they could not change the verdict.
                    for warning in static_result.bandit_warnings:
                        report.issues_found.append(Issue(
                            phase=DebugPhase.STATIC, type="bandit_warning",
                            description=warning, severity="medium", confidence=0.7,
                        ))
                    for finding in static_result.semgrep_findings:
                        report.issues_found.append(Issue(
                            phase=DebugPhase.STATIC, type="semgrep_finding",
                            description=finding, severity="medium", confidence=0.7,
                        ))
                    # A static tool that ran and failed means the static phase did
                    # not fully run, so the verdict must not read as clean.
                    for tool_error in static_result.tool_errors:
                        report.issues_found.append(Issue(
                            phase=DebugPhase.STATIC, type="static_tool_error",
                            description=tool_error, severity="low", confidence=0.9,
                        ))
                    report.phases_completed.append(DebugPhase.STATIC)
                    token_cost += 50
                if "runtime" in phases:
                    runtime_result = Phase1RuntimeDebug.run(code)
                    # Same fix as static, above: patterns_found used to only
                    # feed a local counter, never report.issues_found.
                    # Note: patterns_found is typed List[str] but Phase1RuntimeDebug
                    # actually stores the BugPatternType enum members themselves
                    # (a pre-existing minor type/hint mismatch, not introduced
                    # here) -- normalized to .value below so Issue.type (typed
                    # str) actually gets a string, and so the severity check
                    # isn't silently comparing an enum member to a string
                    # literal (which found while writing this: that comparison
                    # is always False, so the naive version of this line would
                    # have quietly given every runtime pattern "medium"
                    # severity, including unhandled exceptions).
                    for pattern_name in runtime_result.patterns_found:
                        pattern_str = getattr(pattern_name, "value", None) or str(pattern_name)
                        report.issues_found.append(Issue(
                            phase=DebugPhase.RUNTIME, type=pattern_str,
                            description=f"Runtime pattern detected: {pattern_str}",
                            severity="high" if pattern_str == "unhandled_exception" else "medium",
                            confidence=0.85,
                        ))
                    report.phases_completed.append(DebugPhase.RUNTIME)
                    token_cost += 100
                if "testing" in phases:
                    design_result = Phase3DesignReview.run(code)
                    if not design_result.passed:
                        report.issues_found.append(Issue(
                            phase=DebugPhase.TESTING, type="design_review_failed",
                            description="Design review flagged this code (see phase_3_design details)",
                            severity="medium", confidence=0.6,
                        ))
                    report.phases_completed.append(DebugPhase.TESTING)
                    token_cost += 200
            except Exception as e:
                print(f"[MasterDebugger] Python phase analysis error: {e}", file=sys.stderr)
        else:
            if "static" in phases:
                report.phases_completed.append(DebugPhase.STATIC)
                token_cost += 50
            if "runtime" in phases:
                report.phases_completed.append(DebugPhase.RUNTIME)
                token_cost += 100
            if "testing" in phases:
                report.phases_completed.append(DebugPhase.TESTING)
                token_cost += 200
        
        # Phase 2: Formal Verification (with PyProver)
        if "formal" in phases:
            pyprover_result = await self._phase_2_formal(code, language)
            if pyprover_result:
                report.pyprover_result = pyprover_result
                token_cost += 300
            report.phases_completed.append(DebugPhase.FORMAL)

            # Concurrency analysis (race conditions, deadlocks) via the
            # PyProver bridge's verify_async(), source-only so it runs
            # regardless of whether a contract is present.
            async_issues = self._phase_2_async(code, language)
            if async_issues:
                report.issues_found.extend(async_issues)
                token_cost += 100
        
        # ------------------------------------------------------------------
        # Synthesis with explicit conflict resolution (roadmap.md §20/§5).
        #
        # Real bug this replaces: the previous version checked
        # `if report.issues_found:` to decide whether to report issues, but
        # `report.issues_found` only ever contained async-concurrency
        # findings (the static/runtime fix above is what makes this section
        # correct now) -- so whenever async findings were empty, a passing
        # PyProver contract silently produced "✅ VERIFIED" regardless of
        # what static analysis or the runtime trace actually found.
        # Confirmed directly: `undefined_variable_reference_xyz` in a
        # function body with a trivially-true contract produced
        # "✅ VERIFIED" / RiskLevel.LOW even though the runtime trace
        # captured a real NameError.
        #
        # This is exactly the "streams disagree" case roadmap.md §5 flagged
        # as missing (master-debugger v3.0's blind-spot model): a formal
        # contract proves a *narrow* mathematical property, and passing it
        # says nothing about whether the rest of the function body even
        # runs. When that happens now, it's surfaced as an explicit
        # CONFLICT state instead of either stream silently winning.
        # ------------------------------------------------------------------
        total_issues = len(report.issues_found)
        pyprover_verified = bool(report.pyprover_result and report.pyprover_result.get("verified"))

        if total_issues > 0 and pyprover_verified:
            report.overall_health = (
                f"⚠️  CONFLICT: formal verification passed but {total_issues} "
                f"static/runtime issue(s) were found elsewhere -- the contract "
                f"likely doesn't cover the part of the code that's actually broken"
            )
            report.risk_level = RiskLevel.HIGH
            report.confidence_score = 0.5  # lower than either stream's own confidence: they disagree
        elif total_issues > 0:
            report.overall_health = f"⚠️  {total_issues} issue(s) found"
            report.risk_level = RiskLevel.HIGH if total_issues > 3 else RiskLevel.MEDIUM
            report.confidence_score = 0.8
        elif pyprover_verified:
            report.overall_health = "✅ VERIFIED"
            report.risk_level = RiskLevel.LOW
            report.confidence_score = 0.95
        else:
            report.overall_health = "⚠️  INCONCLUSIVE"
            report.risk_level = RiskLevel.MEDIUM
            report.confidence_score = 0.6
        
        report.token_cost = token_cost
        report.recommendations = self._generate_recommendations(report)

        # Phase 5: Auto-generate regression tests when issues were found.
        # "bugs found → tests generated → verify fix" (memory instruction).
        # Only runs for Python code; skipped on error without failing the report.
        if language.lower() == "python" and total_issues > 0:
            try:
                try:
                    from ..test_generator.test_generator import generate_tests
                except ImportError:
                    from test_generator.test_generator import generate_tests  # type: ignore
                tg_result = generate_tests(code, language="python", max_tests=20)
                report.test_suite = tg_result.test_code
                token_cost += 150
            except Exception as e:
                # Non-fatal: the report continues without a test suite, but
                # the failure is recorded and reported, not silently dropped.
                report.test_generation_error = f"{type(e).__name__}: {e}"
                print(f"[MasterDebugger] Phase 5 test generation failed: {report.test_generation_error}", file=sys.stderr)

        return report
    
    async def _phase_2_formal(self, code: str, language: str) -> Optional[Dict[str, Any]]:
        """
        Phase 2: Formal verification using PyProver.
        
        Returns:
            PyProver result dict, or None if not available
        """
        if not self.pyprover_bridge or not self.pyprover_bridge.is_available():
            print(f"[MasterDebugger] PyProver not available (language: {language})", file=sys.stderr)
            return None
        
        try:
            result = self.pyprover_bridge.verify(code, language)
            if result is None:
                return None
            # `result` is a common.interop.UnifiedDebugReport, not a raw PyProver
            # JSON dict - it has no `.verified`/`.template_type`/`.error` attributes.
            # Derive them from the fields it actually has (risk_level, summary).
            verified = result.risk_level.name == "LOW" and result.confidence_score >= 0.9
            error = result.summary if result.risk_level.name == "CRITICAL" else None
            return {
                "verified": verified,
                "template_type": "contract",
                "error": error,
                "summary": result.summary,
                "risk_level": result.risk_level.name,
                "confidence_score": result.confidence_score,
            }
        except Exception as e:
            print(f"[MasterDebugger] PyProver error: {e}", file=sys.stderr)
            return None
    
    def _phase_2_async(self, code: str, language: str) -> List[Issue]:
        """
        Concurrency analysis using PyProver's AsyncVerifier (race conditions,
        deadlocks). Converts common.interop.BugPattern findings into this
        orchestrator's own Issue dataclass.
        """
        if not self.pyprover_bridge or not self.pyprover_bridge.is_available():
            return []
        try:
            result = self.pyprover_bridge.verify_async(code, language)
        except Exception as e:
            print(f"[MasterDebugger] verify_async error: {e}", file=sys.stderr)
            return []
        if result is None or not result.patterns_detected:
            return []
        return [
            Issue(
                phase=DebugPhase.FORMAL,
                type=bp.pattern_type,
                description=bp.description,
                severity=bp.severity.value,
                location=bp.location,
                fix=bp.suggestion or None,
                confidence=bp.confidence,
            )
            for bp in result.patterns_detected
        ]

    def _generate_recommendations(self, report: UnifiedDebugReport) -> List[str]:
        """Generate actionable recommendations based on findings."""
        recommendations = []
        
        if report.pyprover_result and report.pyprover_result.get("verified"):
            recommendations.append("✅ Formal verification passed - code correct for all inputs")
        elif report.pyprover_result and report.pyprover_result.get("error"):
            recommendations.append(f"❌ Fix: {report.pyprover_result['error']}")
        else:
            recommendations.append("⚠️  Run PyProver for formal verification")
        
        if len(report.phases_completed) < 4:
            recommendations.append(f"Enable all phases for comprehensive analysis")
        
        recommendations.append("Add more test cases for edge cases")
        
        return recommendations
    
    async def classify_risk(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Classify code risk level based on static indicators.

        Scores the code across four risk bands by looking for security-
        sensitive patterns (CRITICAL), complexity markers (HIGH), moderate
        constructs (MEDIUM), and trivial code (LOW).  Returns a dict with
        ``risk_level`` (string), ``score`` (0.0-1.0), ``factors`` (list of
        matched indicator descriptions), and a ``recommendation``.
        """
        code_lower = code.lower()
        factors: List[str] = []

        # CRITICAL indicators
        critical_patterns = [
            ("eval(", "eval() - arbitrary code execution"),
            ("exec(", "exec() - arbitrary code execution"),
            ("os.system(", "os.system() - shell injection risk"),
            ("subprocess", "subprocess - command execution"),
            ("pickle.loads", "pickle.loads - deserialisation vulnerability"),
            ("__import__", "__import__ - dynamic import"),
            ("cryptography", "cryptography library - security-critical code"),
            ("hashlib", "hashlib - cryptographic hashing"),
            ("password", "password handling"),
            ("encrypt", "encryption/decryption logic"),
            ("authenticate", "authentication logic"),
            ("socket", "raw socket I/O"),
            ("ssl.", "SSL/TLS - security protocol"),
            ("jwt.", "JWT - token authentication"),
            ("chmod", "file-permission change"),
            ("os.remove", "file deletion"),
            ("shutil.rmtree", "recursive file deletion"),
        ]
        for token, label in critical_patterns:
            if token in code_lower:
                factors.append(f"CRITICAL: {label}")

        if factors:
            return {
                "risk_level": "critical",
                "score": 1.0,
                "factors": factors,
                "recommendation": (
                    "Security-sensitive code detected - run full debug_comprehensive "
                    "with all phases, including formal verification"
                ),
            }

        # HIGH indicators
        high_patterns = [
            ("open(", "file I/O - resource lifecycle risk"),
            ("requests.", "HTTP client - network I/O"),
            ("urllib", "URL/network access"),
            ("database", "database interaction"),
            ("transaction", "transactional logic"),
            ("recursion", "recursive algorithm"),
            ("threading", "threading - concurrency risk"),
            ("asyncio", "async code - concurrency risk"),
            ("multiprocessing", "multiprocessing - IPC risk"),
            ("ctypes", "ctypes - native memory access"),
            ("cffi", "CFFI - native FFI"),
        ]
        line_count = code.count('\n') + 1
        branch_count = code.count('if ') + code.count('elif ') + code.count('while ')
        func_count = code.count('def ') + code.count('fn ') + code.count('func ')

        for token, label in high_patterns:
            if token in code_lower:
                factors.append(f"HIGH: {label}")

        if line_count > 50:
            factors.append(f"HIGH: large function body ({line_count} lines)")
        if branch_count > 5:
            factors.append(f"HIGH: high branching complexity ({branch_count} branches)")
        if func_count > 3:
            factors.append(f"HIGH: multiple function definitions ({func_count})")

        if factors:
            score = min(0.85, 0.55 + 0.05 * len(factors))
            return {
                "risk_level": "high",
                "score": round(score, 2),
                "factors": factors,
                "recommendation": (
                    "Complex or I/O-heavy code - run debug_comprehensive "
                    "through at least Phase 2 (formal verification)"
                ),
            }

        # MEDIUM indicators
        medium_patterns = [
            ("def ", "function definition"),
            ("class ", "class definition"),
            ("for ", "loop construct"),
            ("while ", "loop construct"),
            ("try:", "exception handling"),
            ("raise ", "exception raising"),
        ]
        for token, label in medium_patterns:
            if token in code_lower:
                factors.append(f"MEDIUM: {label}")

        if factors:
            score = min(0.54, 0.25 + 0.05 * len(factors))
            return {
                "risk_level": "medium",
                "score": round(score, 2),
                "factors": factors,
                "recommendation": "Moderate complexity - run Phases 0-1 (static + runtime analysis)",
            }

        # LOW
        return {
            "risk_level": "low",
            "score": 0.1,
            "factors": ["No elevated risk indicators found"],
            "recommendation": "Minimal code - Phase 0 static analysis is sufficient",
        }


master_debugger = MasterDebugger()


async def debug_comprehensive(code: str, language: str = "python", input_data: Optional[Dict[str, Any]] = None, phases: Optional[List[str]] = None) -> Union[UnifiedDebugReport, Exception]:
    return await master_debugger.debug_comprehensive(code, language, input_data, phases)


async def classify_risk(code: str, language: str = "python") -> Dict[str, Any]:
    return await master_debugger.classify_risk(code, language)
