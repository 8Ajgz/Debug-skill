"""
PyProver Integration Bridge for Debug-Suite v2.0

Enables debug-suite to invoke PyProver v12+ for formal verification across 12 languages.
Normalizes PyProver output to debug-suite's UnifiedDebugReport format.

Supported languages via PyProver:
  - Python, JavaScript, TypeScript
  - Rust, C (Safe Subset), C++20
  - Go, Java, C#
  - WebAssembly (WASM), NASM, FASM

This module provides graceful degradation: if PyProver is not installed,
all methods return None or empty results, allowing debug-suite to continue
with local analysis only.
"""

import sys
from typing import Optional, Dict, List, Any, Union

from .interop import (
    UnifiedDebugReport,
    Variable,
    Mutation,
    BugPattern,
    BugSeverity,
    RiskLevel,
    LanguageType,
    ExecutionEvent,
    ComponentType,
)


# ============================================================================
# PyProver Availability Detection
# ============================================================================

def detect_pyprover_installed() -> bool:
    """
    Check if PyProver is available, either as the bundled sibling package
    (src/pyprover, the common case inside this skill) or as an externally
    installed top-level package.
    """
    try:
        from .. import pyprover  # noqa: F401  (bundled sibling package)
        return True
    except ImportError:
        pass
    try:
        import pyprover  # noqa: F401  (externally installed package)
        return True
    except ImportError:
        return False


def _import_pyprover_module():
    """Return the actual pyprover module (bundled or external), or None."""
    try:
        from .. import pyprover
        return pyprover
    except ImportError:
        pass
    try:
        import pyprover
        return pyprover
    except ImportError:
        return None


PYPROVER_AVAILABLE = detect_pyprover_installed()


# ============================================================================
# PyProver Output Models (Minimal - what we actually use)
# ============================================================================

class PyProverResult:
    """Minimal representation of PyProver formal verification result."""
    
    def __init__(
        self,
        verified: bool,
        template_type: Optional[str] = None,
        proof_time: float = 0.0,
        error: Optional[str] = None,
        constraints: Optional[List[str]] = None,
    ):
        self.verified = verified
        self.template_type = template_type
        self.proof_time = proof_time
        self.error = error
        self.constraints = constraints or []
    
    @classmethod
    def from_pyprover_json(cls, data: Dict[str, Any]) -> "PyProverResult":
        """Parse PyProver's JSON output format."""
        return cls(
            verified=data.get("verified", False),
            template_type=data.get("template_type"),
            proof_time=data.get("proof_time", 0.0),
            error=data.get("error"),
            constraints=data.get("constraints", []),
        )


# ============================================================================
# Language Detection & Routing
# ============================================================================

LANGUAGE_FILE_EXTENSIONS = {
    ".py": LanguageType.PYTHON,
    ".js": LanguageType.JAVASCRIPT,
    ".ts": LanguageType.TYPESCRIPT,
    ".jsx": LanguageType.JAVASCRIPT,
    ".tsx": LanguageType.TYPESCRIPT,
    ".rs": LanguageType.RUST,
    ".cpp": LanguageType.CPP,
    ".cc": LanguageType.CPP,
    ".cxx": LanguageType.CPP,
    ".c++": LanguageType.CPP,
    ".h": LanguageType.CPP,
    ".hpp": LanguageType.CPP,
    ".go": LanguageType.GO,
    ".java": LanguageType.JAVA,
}


# ============================================================================
# PyProver Bridge
# ============================================================================

class PyProverBridge:
    """
    Facade for invoking PyProver from debug-suite.
    
    Handles:
    - Dynamic import (graceful if PyProver not installed)
    - Language detection and routing
    - Output format conversion to UnifiedDebugReport
    - Error handling and timeouts
    
    Usage:
        bridge = PyProverBridge(use_pyprover=True)
        report = bridge.verify(code, language="python")
        if report:
            print(report.risk_level)
    """
    
    def __init__(self, use_pyprover: bool = True, timeout_seconds: int = 30):
        """
        Initialize PyProver bridge.
        
        Args:
            use_pyprover: If False, always return None (for testing)
            timeout_seconds: Max time to wait for PyProver verification
        """
        self.enabled = use_pyprover and PYPROVER_AVAILABLE
        self.timeout_seconds = timeout_seconds
        self._pyprover_module = _import_pyprover_module() if self.enabled else None
    
    def is_available(self) -> bool:
        """Check if PyProver is available and enabled."""
        return self.enabled
    
    def get_supported_languages(self) -> List[LanguageType]:
        """Return list of languages supported via PyProver."""
        if not self.enabled:
            return []
        return [
            LanguageType.PYTHON,
            LanguageType.JAVASCRIPT,
            LanguageType.TYPESCRIPT,
            LanguageType.RUST,
            LanguageType.C,
            LanguageType.CPP,
            LanguageType.GO,
            LanguageType.JAVA,
            LanguageType.CSHARP,
            LanguageType.WASM,
            LanguageType.ASSEMBLY,
        ]
    
    def verify(
        self,
        code: str,
        language: str,
        function_name: Optional[str] = None,
    ) -> Optional[UnifiedDebugReport]:
        """
        Invoke PyProver for formal verification.
        
        Args:
            code: Source code to verify
            language: Language name (e.g., "python", "rust", "cpp")
            function_name: Specific function to verify (optional)
        
        Returns:
            UnifiedDebugReport with verification results, or None if PyProver unavailable
        """
        if not self.enabled:
            return None

        try:
            if self._pyprover_module is None:
                return None

            raw_result = self._pyprover_module.verify_contract(code, language=language)
            pyprover_result = self._adapt_local_result(raw_result)
            return self._convert_to_unified_report(pyprover_result, language, code=code)

        except Exception as e:
            # Log but don't crash - debug-suite continues without PyProver
            print(f"[PyProverBridge] Warning: {e}", file=sys.stderr)
            return None
    
    def _convert_to_unified_report(
        self,
        pyprover_result: Dict[str, Any],
        language: str,
        code: str = "",
    ) -> UnifiedDebugReport:
        """
        Convert a raw PyProver JSON result into debug-suite's UnifiedDebugReport.
        
        Classification rules:
          - verified=True                      -> LOW risk, confidence 1.0, "VERIFIED"
          - verified=False with an error        -> CRITICAL risk, confidence 0.0, "FAILED"
          - verified=False with no error (i.e. inconclusive proof) -> MEDIUM risk,
            confidence 0.5, "INCONCLUSIVE"
        """
        result = PyProverResult.from_pyprover_json(pyprover_result)
        lang_type = self._map_language_type(language) or LanguageType.PYTHON
        
        if result.verified:
            risk_level = RiskLevel.LOW
            confidence = 1.0
            summary = f"VERIFIED: {result.template_type or 'proof'} succeeded in {result.proof_time:.2f}s"
        elif result.error:
            risk_level = RiskLevel.CRITICAL
            confidence = 0.0
            summary = f"FAILED: {result.error}"
        else:
            risk_level = RiskLevel.MEDIUM
            confidence = 0.5
            summary = f"INCONCLUSIVE: proof did not complete ({result.template_type or 'unknown template'})"
        
        return UnifiedDebugReport(
            component=ComponentType.PYPROVER,
            language=lang_type,
            code=code,
            risk_level=risk_level,
            confidence_score=confidence,
            summary=summary,
        )
    
    def _map_language_type(self, pyprover_lang: Union[str, LanguageType]) -> Optional[LanguageType]:
        """Map a PyProver language string (e.g. 'csharp', 'nasm') to LanguageType.

        Also accepts a LanguageType enum directly and returns it unchanged.
        """
        if isinstance(pyprover_lang, LanguageType):
            return pyprover_lang
        mapping = {
            "python": LanguageType.PYTHON,
            "javascript": LanguageType.JAVASCRIPT,
            "typescript": LanguageType.TYPESCRIPT,
            "rust": LanguageType.RUST,
            "c": LanguageType.C,
            "cpp": LanguageType.CPP,
            "c++": LanguageType.CPP,
            "go": LanguageType.GO,
            "java": LanguageType.JAVA,
            "csharp": LanguageType.CSHARP,
            "c#": LanguageType.CSHARP,
            "webassembly": LanguageType.WASM,
            "wasm": LanguageType.WASM,
            "nasm": LanguageType.ASSEMBLY,
            "fasm": LanguageType.ASSEMBLY,
            "assembly": LanguageType.ASSEMBLY,
        }
        return mapping.get(pyprover_lang.lower())
    
    def _adapt_local_result(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adapt the bundled pyprover.verify_contract() output shape
        ({verified, preconditions_ok, postconditions_ok, details: [str, ...]})
        to the PyProverResult.from_pyprover_json() shape this bridge expects
        ({verified, template_type, proof_time, error, constraints}).
        """
        details = raw_result.get("details", [])
        verified = raw_result.get("verified", False)
        # A failed verification reports its reason as the last detail entry
        # (e.g. "Z3 solver not available: ..." or "Verification error: ...").
        error = None
        # An inconclusive result (nothing proven) is not a failure, so it gets no error
        # and the bridge reports it as INCONCLUSIVE rather than FAILED.
        if not verified and details and not raw_result.get("inconclusive"):
            error = details[-1]
        return {
            "verified": verified,
            "template_type": "contract",
            "proof_time": 0.0,
            "error": error,
            "constraints": details,
        }

    def verify_async(
        self,
        code: str,
        language: str = "python",
    ) -> Optional[UnifiedDebugReport]:
        """
        Run PyProver's async/concurrency analysis (race conditions, deadlocks)
        directly from source. Source-only entry point - unlike verify(), which
        proves contracts, this surfaces concurrency BugPatterns without
        requiring a caller-constructed AsyncContract.

        Returns None if PyProver/the bundled async_verifier is unavailable.
        """
        if not self.enabled or self._pyprover_module is None:
            return None
        async_verifier = getattr(self._pyprover_module, "async_verifier", None)
        if async_verifier is None:
            return None

        lang_type = self._map_language_type(language) or LanguageType.PYTHON

        patterns = async_verifier.detect_async_patterns(code, language)
        if not patterns:
            # Not async code - nothing for this analysis to do.
            return UnifiedDebugReport(
                component=ComponentType.PYPROVER,
                language=lang_type,
                code=code,
                risk_level=RiskLevel.LOW,
                confidence_score=1.0,
                summary="No async patterns detected; concurrency analysis skipped",
            )

        concurrent_vars = async_verifier.detect_concurrent_variables(code, language)
        race_issues = async_verifier.detect_race_conditions(code, concurrent_vars)
        deadlock_issues = async_verifier.detect_deadlock_patterns(code)

        bug_patterns: List[BugPattern] = []
        for issue in race_issues:
            bug_patterns.append(BugPattern(
                pattern_type=issue.value if hasattr(issue, "value") else str(issue),
                severity=BugSeverity.HIGH,
                location="async function",
                description=f"Potential {issue.value} on concurrently-accessed variable(s): {', '.join(concurrent_vars) or 'unknown'}",
                component=ComponentType.PYPROVER,
                language=lang_type,
                suggestion="Protect concurrent access with a lock or atomic operation",
                confidence=0.6,
            ))
        for issue in deadlock_issues:
            bug_patterns.append(BugPattern(
                pattern_type=issue.value if hasattr(issue, "value") else str(issue),
                severity=BugSeverity.HIGH,
                location="async function",
                description=f"Potential {issue.value}: lock held across an await point",
                component=ComponentType.PYPROVER,
                language=lang_type,
                suggestion="Release locks before awaiting, or use timeout-based acquisition",
                confidence=0.6,
            ))

        if bug_patterns:
            risk_level = RiskLevel.HIGH
            confidence = 0.6
            summary = f"{len(bug_patterns)} concurrency issue(s) found: " + \
                      ", ".join(sorted({bp.pattern_type for bp in bug_patterns}))
        else:
            risk_level = RiskLevel.LOW
            confidence = 0.7
            summary = f"Async patterns found ({len(patterns)}); no concurrency issues detected"

        return UnifiedDebugReport(
            component=ComponentType.PYPROVER,
            language=lang_type,
            code=code,
            patterns_detected=bug_patterns,
            risk_level=risk_level,
            confidence_score=confidence,
            summary=summary,
        )

    def batch_verify(
        self,

        code: str,
        language: str,
    ) -> Optional[Dict[str, UnifiedDebugReport]]:
        """
        Verify all functions in code.
        
        Args:
            code: Source code
            language: Language name
        
        Returns:
            Dict mapping function names → UnifiedDebugReport, or None if unavailable
        """
        if not self.enabled or self._pyprover_module is None:
            return None

        results: Dict[str, UnifiedDebugReport] = {}

        if language.lower() != "python":
            # The bundled ContractVerifier's pre:/post:/inv: comment parser is
            # language-agnostic text scanning, but per-function splitting below
            # uses Python's ast module, so batch mode is Python-only for now.
            # Single-function verify() still works for any language.
            report = self.verify(code, language)
            if report is not None:
                results["__module__"] = report
            return results or None

        import ast
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            print(f"[PyProverBridge] batch_verify: could not parse code: {e}", file=sys.stderr)
            return None

        function_nodes = [
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if not function_nodes:
            return None

        for node in function_nodes:
            func_source = ast.get_source_segment(code, node) or ""
            report = self.verify(func_source, language, function_name=node.name)
            if report is not None:
                results[node.name] = report

        return results or None
    
    def detect_language(self, code: str, filename: Optional[str] = None) -> Optional[LanguageType]:
        """
        Detect language from code or filename.
        
        Args:
            code: Source code
            filename: Optional filename with extension
        
        Returns:
            Detected LanguageType, or None if unknown
        """
        # Try extension-based detection first
        if filename:
            for ext, lang_type in LANGUAGE_FILE_EXTENSIONS.items():
                if filename.endswith(ext):
                    return lang_type
        
        # Fallback: heuristic detection
        return self._heuristic_language_detection(code)
    
    def _heuristic_language_detection(self, code: str) -> Optional[LanguageType]:
        """Fallback: simple heuristic language detection."""
        code_lower = code.lower()
        
        # Python indicators
        if "def " in code and ("import " in code or "from " in code):
            return LanguageType.PYTHON
        if code.strip().startswith("@"):
            return LanguageType.PYTHON
        
        # JavaScript/TypeScript indicators
        if "function " in code or "const " in code or "let " in code:
            if "fn " not in code:  # Avoid Rust match
                if ": Promise" in code or "async " in code:
                    return LanguageType.TYPESCRIPT
                return LanguageType.JAVASCRIPT
        
        # Rust indicators
        if "fn " in code and ("let " in code or "mut " in code):
            return LanguageType.RUST
        
        # C++ indicators
        if "#include" in code:
            return LanguageType.CPP
        
        # Go indicators
        if "func " in code and "package " in code:
            return LanguageType.GO
        
        # Java indicators
        if "public class " in code or "public static void main" in code:
            return LanguageType.JAVA
        
        return None

    def verify_ffi(
        self,
        code: str,
        caller_language: str = "python",
        callee_language: str = "c",
    ) -> Optional[Dict]:
        """Verify FFI boundary safety using the bundled FFIVerifier.

        Checks type compatibility, memory ownership, and lifetime safety
        across a foreign-function interface. The FFIVerifier extracts
        function signatures from the source and builds an FFIContract
        automatically using heuristics.

        Returns a dict with keys: verified, issues, recommendations, or
        None if the FFIVerifier is unavailable.
        """
        if self._pyprover_module is None:
            return None
        ffi_verifier = getattr(self._pyprover_module, "ffi_verifier", None)
        if ffi_verifier is None:
            return None
        try:
            from ..pyprover.ffi_verifier import FFIContract, FFISignature, FFIType
        except ImportError:
            try:
                from pyprover.ffi_verifier import FFIContract, FFISignature, FFIType  # type: ignore
            except ImportError:
                return {"verified": False, "issues": ["FFIVerifier not importable"], "recommendations": []}

        # Heuristic: build a minimal FFIContract from the code
        # Extract the first function signature found
        import re
        sig_pattern = re.compile(
            r'(?:def|void|int|char\*|bool)\s+(\w+)\s*\(([^)]*)\)',
            re.MULTILINE
        )
        m = sig_pattern.search(code)
        if m is None:
            return {
                "verified": False,
                "issues": ["No function signature found for FFI analysis"],
                "recommendations": ["Add an explicit function signature"],
            }

        func_name = m.group(1)
        try:
            # Build a minimal contract and verify it
            sig = FFISignature(
                function_name=func_name,
                parameters={},
                return_type=FFIType.VOID,
                caller_language=caller_language,
                callee_language=callee_language,
            )
            contract = FFIContract(
                caller_signature=sig,
                callee_signature=sig,
            )
            result = ffi_verifier.verify(contract)
            return {
                "verified": getattr(result, "is_safe", False),
                "issues": getattr(result, "violations", []),
                "recommendations": getattr(result, "recommendations", []),
                "function": func_name,
            }
        except Exception as e:
            return {
                "verified": False,
                "issues": [f"FFI verification error: {e}"],
                "recommendations": [],
            }

    def verify_loop_invariants(
        self,
        code: str,
        param_names: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        """Verify loop invariants annotated in code using Z3.

        Looks for  # Invariant: <expr>  comments and checks INIT and
        PRESERVATION proof obligations using the bundled LoopVerifier.

        Returns a summary dict, or None if Z3 is unavailable.
        """
        try:
            from ..pyprover.loop_verifier import LoopVerifier
        except ImportError:
            try:
                from pyprover.loop_verifier import LoopVerifier  # type: ignore
            except ImportError:
                return None
        report = LoopVerifier().verify_source(code, param_names=param_names or [])
        return {
            "invariants_found": report.invariants_found,
            "all_verified": report.all_verified,
            "z3_available": report.z3_available,
            "summary": report.summary(),
            "results": [
                {
                    "invariant": r.invariant,
                    "init_holds": r.init_holds,
                    "preservation_holds": r.preservation_holds,
                    "fully_verified": r.fully_verified,
                    "skipped": r.skipped,
                    "skip_reason": r.skip_reason,
                    "error": r.error,
                }
                for r in report.results
            ],
        }

    def verify_equivalence(
        self,
        code_a: str,
        func_a: str,
        code_b: str,
        func_b: str,
        max_unroll: int = 64,
    ) -> Optional[Dict[str, Any]]:
        """Prove whether two functions compute the same result for all
        inputs, using the bundled equivalence_verifier (symbolic execution
        + Z3, supported subset: straight-line/branching arithmetic code,
        plus bounded 'for x in range(N)' loops — see
        pyprover/equivalence_verifier.py's module docstring for the exact
        scope and what's explicitly NOT supported).

        Returns a dict with keys: status ("decided"/"unsupported"/"unknown"),
        equivalent (bool or None), counterexample, reason, summary. Returns
        None only if the bundled pyprover module itself is unavailable —
        an out-of-scope construct in the code is NOT a None return, it's
        status="unsupported" with a reason, so callers can distinguish
        "PyProver isn't installed" from "this specific code can't be
        analyzed."
        """
        if self._pyprover_module is None:
            return None
        try:
            from ..pyprover.equivalence_verifier import verify_function_equivalence
        except ImportError:
            try:
                from pyprover.equivalence_verifier import verify_function_equivalence  # type: ignore
            except ImportError:
                return None

        result = verify_function_equivalence(code_a, func_a, code_b, func_b, max_unroll=max_unroll)
        return {
            "status": result.status,
            "equivalent": result.equivalent,
            "counterexample": result.counterexample,
            "reason": result.reason,
            "proof_a": result.proof_a,
            "proof_b": result.proof_b,
            "summary": result.summary(),
        }

    def simplify_function_code(
        self,
        code: str,
        func_name: str,
        max_unroll: int = 64,
    ) -> Optional[Dict[str, Any]]:
        """Derive an algebraically simplified equivalent of a function's
        return value via the bundled equivalence_verifier's Z3-backed
        simplify_function(). See that function's docstring: the result is
        a Z3 expression's string form (what the code reduces to), not
        auto-generated Python — turning it back into idiomatic code is a
        manual follow-up.

        Returns a dict with keys: status, original_expr, simplified_expr,
        reason, summary. Returns None only if pyprover itself is
        unavailable.
        """
        if self._pyprover_module is None:
            return None
        try:
            from ..pyprover.equivalence_verifier import simplify_function
        except ImportError:
            try:
                from pyprover.equivalence_verifier import simplify_function  # type: ignore
            except ImportError:
                return None

        result = simplify_function(code, func_name, max_unroll=max_unroll)
        return {
            "status": result.status,
            "original_expr": result.original_expr,
            "simplified_expr": result.simplified_expr,
            "reason": result.reason,
            "summary": result.summary(),
        }



# ============================================================================
# Module-Level Convenience Functions
# ============================================================================

_bridge: Optional[PyProverBridge] = None


def get_bridge(use_pyprover: bool = True) -> PyProverBridge:
    """Get or create the default PyProver bridge."""
    global _bridge
    if _bridge is None:
        _bridge = PyProverBridge(use_pyprover=use_pyprover)
    return _bridge


def invoke_pyprover(
    code: str,
    language: str,
    function_name: Optional[str] = None,
) -> Optional[UnifiedDebugReport]:
    """
    Convenience function: invoke PyProver for a code snippet.
    
    Returns None if PyProver not available.
    """
    return get_bridge().verify(code, language, function_name)


def detect_language(code: str, filename: Optional[str] = None) -> Optional[LanguageType]:
    """
    Convenience function: detect code language.
    
    Uses PyProver if available, falls back to heuristics.
    """
    return get_bridge().detect_language(code, filename)
