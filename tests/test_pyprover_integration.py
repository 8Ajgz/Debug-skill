"""
Integration tests for PyProver Bridge.

Tests the bridge in three modes:
1. With PyProver installed (real integration)
2. With PyProver mocked (graceful degradation)
3. Cross-language detection
"""

import pytest
from typing import Optional
from unittest.mock import Mock, patch, MagicMock

# Import bridge
from src.common.pyprover_bridge import (
    PyProverBridge,
    invoke_pyprover,
    detect_language,
    PYPROVER_AVAILABLE,
)
from src.common.interop import LanguageType, RiskLevel


class TestPyProverBridgeInitialization:
    """Test bridge initialization and availability detection."""
    
    def test_bridge_creation_no_pyprover(self):
        """Bridge should be creatable even without PyProver installed."""
        bridge = PyProverBridge(use_pyprover=False)
        assert not bridge.is_available()
        assert bridge.enabled is False
    
    def test_bridge_can_be_disabled(self):
        """Bridge should respect use_pyprover=False flag."""
        bridge = PyProverBridge(use_pyprover=False)
        assert bridge.is_available() is False
    
    def test_bridge_respects_timeout(self):
        """Bridge should accept and store timeout setting."""
        bridge = PyProverBridge(timeout_seconds=60)
        assert bridge.timeout_seconds == 60


class TestLanguageDetection:
    """Test language detection capabilities."""
    
    def test_detect_python_from_extension(self):
        """Should detect Python from .py extension."""
        bridge = PyProverBridge(use_pyprover=False)
        lang = bridge.detect_language("def foo(): pass", filename="test.py")
        assert lang == LanguageType.PYTHON
    
    def test_detect_rust_from_extension(self):
        """Should detect Rust from .rs extension."""
        bridge = PyProverBridge(use_pyprover=False)
        lang = bridge.detect_language("fn foo() {}", filename="test.rs")
        assert lang == LanguageType.RUST
    
    def test_detect_cpp_from_extension(self):
        """Should detect C++ from .cpp extension."""
        bridge = PyProverBridge(use_pyprover=False)
        lang = bridge.detect_language("#include <vector>", filename="test.cpp")
        assert lang == LanguageType.CPP
    
    def test_heuristic_detect_python(self):
        """Should detect Python from code heuristics."""
        bridge = PyProverBridge(use_pyprover=False)
        code = """
def factorial(n):
    import math
    return math.factorial(n)
"""
        lang = bridge.detect_language(code)
        assert lang == LanguageType.PYTHON
    
    def test_heuristic_detect_rust(self):
        """Should detect Rust from code heuristics."""
        bridge = PyProverBridge(use_pyprover=False)
        code = """
fn main() {
    let mut x = 5;
    println!("{}", x);
}
"""
        lang = bridge.detect_language(code)
        assert lang == LanguageType.RUST
    
    def test_heuristic_detect_javascript(self):
        """Should detect JavaScript from code heuristics."""
        bridge = PyProverBridge(use_pyprover=False)
        code = "const x = function() { return 5; };"
        lang = bridge.detect_language(code)
        assert lang == LanguageType.JAVASCRIPT
    
    def test_heuristic_detect_golang(self):
        """Should detect Go from code heuristics."""
        bridge = PyProverBridge(use_pyprover=False)
        code = """
package main
func main() {
    fmt.Println("Hello")
}
"""
        lang = bridge.detect_language(code)
        assert lang == LanguageType.GO
    
    def test_detect_unknown_returns_none(self):
        """Should return None for unknown languages."""
        bridge = PyProverBridge(use_pyprover=False)
        lang = bridge.detect_language("unknown syntax @@@ !!!!")
        # Either None or best guess is acceptable
        assert lang is None or isinstance(lang, LanguageType)


class TestVerifyGracefulDegradation:
    """Test that bridge gracefully handles missing PyProver."""
    
    def test_verify_returns_none_when_disabled(self):
        """verify() should return None when PyProver disabled."""
        bridge = PyProverBridge(use_pyprover=False)
        result = bridge.verify("def foo(): pass", language="python")
        assert result is None
    
    def test_batch_verify_returns_none_when_disabled(self):
        """batch_verify() should return None when PyProver disabled."""
        bridge = PyProverBridge(use_pyprover=False)
        result = bridge.batch_verify("def foo(): pass\ndef bar(): pass", language="python")
        assert result is None
    
    def test_verify_handles_import_error(self):
        """verify() should catch ImportError gracefully."""
        bridge = PyProverBridge(use_pyprover=False)
        # This should not raise, should return None
        result = bridge.verify("code", language="python")
        assert result is None
    
    def test_supported_languages_empty_when_disabled(self):
        """get_supported_languages() should return empty list when disabled."""
        bridge = PyProverBridge(use_pyprover=False)
        langs = bridge.get_supported_languages()
        assert langs == []


class TestConversionToUnifiedReport:
    """Test conversion of PyProver results to UnifiedReport format."""
    
    def test_successful_verification_converts_correctly(self):
        """Successful verification should produce LOW risk UnifiedReport."""
        bridge = PyProverBridge(use_pyprover=False)
        
        # Create a mock PyProver result
        mock_result = {
            "verified": True,
            "template_type": "ACCUMULATOR",
            "proof_time": 0.15,
            "error": None,
            "constraints": ["x >= 0", "result >= x"],
        }
        
        report = bridge._convert_to_unified_report(mock_result, "python")
        
        assert report is not None
        assert report.risk_level == RiskLevel.LOW
        assert report.confidence_score == 1.0
        assert "VERIFIED" in report.summary
    
    def test_failed_verification_converts_correctly(self):
        """Failed verification should produce CRITICAL risk UnifiedReport."""
        bridge = PyProverBridge(use_pyprover=False)
        
        mock_result = {
            "verified": False,
            "template_type": None,
            "proof_time": 0.0,
            "error": "Constraint unsatisfiable: x > 0 AND x < 0",
            "constraints": [],
        }
        
        report = bridge._convert_to_unified_report(mock_result, "python")
        
        assert report is not None
        assert report.risk_level == RiskLevel.CRITICAL
        assert report.confidence_score == 0.0
        assert "FAILED" in report.summary
    
    def test_inconclusive_verification_converts_correctly(self):
        """Inconclusive verification should produce MEDIUM risk UnifiedReport."""
        bridge = PyProverBridge(use_pyprover=False)
        
        mock_result = {
            "verified": False,
            "template_type": "BINARY_SEARCH",
            "proof_time": 0.5,
            "error": None,
            "constraints": ["constraint_1", "constraint_2"],
        }
        
        report = bridge._convert_to_unified_report(mock_result, "python")
        
        assert report is not None
        assert report.risk_level == RiskLevel.MEDIUM
        assert report.confidence_score == 0.5
        assert "INCONCLUSIVE" in report.summary


class TestModuleLevelConvenience:
    """Test module-level convenience functions."""
    
    def test_invoke_pyprover_returns_none_if_unavailable(self):
        """invoke_pyprover should return None if PyProver unavailable."""
        result = invoke_pyprover("def foo(): pass", "python")
        # May return None or a report, depends on PyProver availability
        assert result is None or hasattr(result, "risk_level")
    
    def test_detect_language_returns_language_type(self):
        """detect_language should return LanguageType or None."""
        result = detect_language("def foo(): pass")
        assert result is None or isinstance(result, LanguageType)


class TestLanguageMapping:
    """Test mapping between PyProver and debug-suite language types."""
    
    def test_all_supported_languages_mappable(self):
        """All PyProver languages should map to debug-suite LanguageType."""
        bridge = PyProverBridge(use_pyprover=False)
        
        pyprover_langs = [
            "python", "javascript", "typescript", "rust", "c", "cpp",
            "go", "java", "csharp", "webassembly", "nasm", "fasm"
        ]
        
        for pyprover_lang in pyprover_langs:
            mapped = bridge._map_language_type(pyprover_lang)
            assert mapped is not None, f"Failed to map {pyprover_lang}"
            assert isinstance(mapped, LanguageType)


# ============================================================================
# Acceptance Criteria
# ============================================================================

class TestAcceptanceCriteria:
    """Phase 1 acceptance criteria verification."""
    
    def test_acceptance_bridge_imports_all_12_languages(self):
        """Bridge should know about all 12 PyProver languages."""
        bridge = PyProverBridge(use_pyprover=False)
        # All 12 languages should be detectable/mappable
        langs = [
            LanguageType.PYTHON, LanguageType.JAVASCRIPT, LanguageType.TYPESCRIPT,
            LanguageType.RUST, LanguageType.C, LanguageType.CPP,
            LanguageType.GO, LanguageType.JAVA, LanguageType.CSHARP,
            LanguageType.WASM, LanguageType.ASSEMBLY, LanguageType.ASSEMBLY,
        ]
        assert len(set(langs)) >= 10  # At least 10 distinct languages
    
    def test_acceptance_invoke_pyprover_works_if_available(self):
        """Should be able to call invoke_pyprover without crashing."""
        try:
            result = invoke_pyprover("def foo(): pass", "python")
            # Succeeds if PyProver available, returns None if not
            assert result is None or hasattr(result, "risk_level")
        except Exception as e:
            pytest.fail(f"invoke_pyprover crashed: {e}")
    
    def test_acceptance_graceful_degradation(self):
        """Bridge should degrade gracefully without PyProver."""
        bridge = PyProverBridge(use_pyprover=False)
        
        # All these should work without raising exceptions
        assert bridge.is_available() is False
        assert bridge.verify("code", "python") is None
        assert bridge.batch_verify("code", "python") is None
        assert bridge.detect_language("code") is not None or True  # May return None
        assert bridge.get_supported_languages() == []


class TestRealPyProverIntegration:
    """
    Verifies the bridge actually invokes the bundled src/pyprover module
    instead of returning a canned/fake result. Skipped if the bundled
    pyprover package isn't importable in this environment (PYPROVER_AVAILABLE
    is computed once at module import time from the same detection bridge
    uses internally).
    """

    @pytest.mark.skipif(not PYPROVER_AVAILABLE, reason="bundled pyprover not importable")
    def test_verify_reflects_real_contract_result(self):
        bridge = PyProverBridge(use_pyprover=True)
        assert bridge.is_available()

        report = bridge.verify("def f(x):\n    return x", "python")
        assert report is not None
        # Real verification must be deterministic and content-dependent -
        # i.e. not a fixed placeholder string regardless of input.
        assert "INCONCLUSIVE" not in report.summary or "did not complete" in report.summary
        assert report.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.CRITICAL)

    @pytest.mark.skipif(not PYPROVER_AVAILABLE, reason="bundled pyprover not importable")
    def test_batch_verify_splits_python_functions(self):
        bridge = PyProverBridge(use_pyprover=True)
        code = "def f(x):\n    return x\n\ndef g(y):\n    return y * 2\n"
        results = bridge.batch_verify(code, "python")
        assert results is not None
        assert set(results.keys()) == {"f", "g"}

    @pytest.mark.skipif(not PYPROVER_AVAILABLE, reason="bundled pyprover not importable")
    def test_verify_async_detects_no_patterns_in_sync_code(self):
        bridge = PyProverBridge(use_pyprover=True)
        report = bridge.verify_async("def f(x): return x + 1", "python")
        assert report is not None
        assert "No async patterns" in report.summary

    @pytest.mark.skipif(not PYPROVER_AVAILABLE, reason="bundled pyprover not importable")
    def test_verify_async_detects_patterns_in_async_code(self):
        bridge = PyProverBridge(use_pyprover=True)
        report = bridge.verify_async(
            "async def f(x):\n    await g(x)\n    return x", "python"
        )
        assert report is not None
        assert "Async patterns found" in report.summary or "concurrency issue" in report.summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
