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
from typing import Optional, Dict, List, Any

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
    """Check if PyProver skill/package is installed and importable."""
    try:
        import pyprover
        return True
    except ImportError:
        return False


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
        self._pyprover_module = None
    
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
            # NOTE: real PyProver invocation (self._pyprover_module.verify(...))
            # is not wired up in this environment. When PyProver is installed,
            # replace this block with the actual call and pass its JSON result
            # straight into _convert_to_unified_report.
            pyprover_result = self._create_placeholder_result(language)
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
    
    def _map_language_type(self, pyprover_lang: str) -> Optional[LanguageType]:
        """Map a PyProver language string (e.g. 'csharp', 'nasm') to LanguageType."""
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
    
    def _create_placeholder_result(self, language: str) -> Dict[str, Any]:
        """Raw-result stand-in used until a real PyProver call is wired up."""
        return {
            "verified": False,
            "template_type": None,
            "proof_time": 0.0,
            "error": None,
            "constraints": [],
        }
    
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
        if not self.enabled:
            return None
        
        return None
    
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
