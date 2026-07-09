"""
Integration tests for the verification-debugging-suite.

Tests complete workflows combining multiple components:
- Master debugger orchestration
- Python-debug + formal verification
- Test generation + execution
"""

import pytest


class TestMasterDebuggerIntegration:
    """Integration tests for master debugger workflows."""
    
    @pytest.mark.integration
    def test_critical_code_full_workflow(self):
        """Test complete workflow on critical code."""
        from src.master_debugger.orchestrator_v5 import MasterDebuggerV5
        
        code = """
import socket
def connect(host, port):
    s = socket.socket()
    s.connect((host, port))
    return s
"""
        
        debugger = MasterDebuggerV5()
        report = debugger.debug(code)
        
        # Should identify as critical
        # NOTE: value was 'critical' (lowercase) before the v2.6.0 RiskLevel
        # unification (see roadmap.md §11.6/CHANGELOG.md) - master_debugger
        # used to define its own lowercase-valued RiskLevel, separate from
        # common.interop.RiskLevel (uppercase) used by every per-language
        # debugger. Now unified onto common.interop's uppercase values.
        assert report.risk_level.value == 'CRITICAL'
        # Should run multiple phases
        assert len(report.phases_executed) >= 2
    
    @pytest.mark.integration
    def test_simple_code_workflow(self):
        """Test workflow on simple code."""
        from src.master_debugger.orchestrator_v5 import MasterDebuggerV5
        
        code = "def double(x): return x * 2"
        
        debugger = MasterDebuggerV5()
        report = debugger.debug(code)
        
        assert report is not None
        assert report.phases_executed is not None


class TestDebugAndTestIntegration:
    """Integration tests combining debugging and testing."""
    
    @pytest.mark.integration
    def test_debug_then_generate_tests(self):
        """Test debugging followed by test generation."""
        from src.master_debugger.orchestrator_v5 import MasterDebuggerV5
        from src.test_generator import TestGenerator
        
        code = """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
"""
        
        # Step 1: Debug
        debugger = MasterDebuggerV5()
        debug_report = debugger.debug(code)
        assert debug_report is not None
        
        # Step 2: Generate tests
        generator = TestGenerator()
        tests = generator.generate_tests(code, language="python")
        assert tests is not None
    
    @pytest.mark.integration
    def test_trace_and_analyze_patterns(self):
        """Test execution tracing followed by pattern analysis."""
        from src.python_debug.debug_report import execute_with_debug
        
        code = """
items = [1, 2, 3]
result = []
for item in items:
    result.append(item * 2)
"""
        
        report = execute_with_debug(code)
        
        assert report.execution_complete
        assert 'items' in report.final_state
        assert 'result' in report.final_state


class TestEndToEndWorkflow:
    """Complete end-to-end testing workflows."""
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_complete_verification_workflow(self):
        """Test complete verification workflow."""
        from src.master_debugger.orchestrator_v5 import MasterDebuggerV5
        from src.python_debug.debug_report import execute_with_debug
        from src.test_generator import TestGenerator
        from src.pyprover.contract_verifier import ContractVerifier
        
        code = """
def add(a, b):
    return a + b
"""
        
        # Phase 1: Debug with master-debugger
        debugger = MasterDebuggerV5()
        debug_report = debugger.debug(code)
        assert debug_report is not None
        
        # Phase 2: Trace execution
        trace_report = execute_with_debug(code)
        assert trace_report.execution_complete
        
        # Phase 3: Formal verification
        verifier = ContractVerifier()
        verify_result = verifier.verify_contract(code)
        assert verify_result is not None
        
        # Phase 4: Generate tests
        generator = TestGenerator()
        tests = generator.generate_tests(code, language="python")
        assert tests is not None


class TestComponentIntegration:
    """Test integration between components."""
    
    @pytest.mark.integration
    def test_all_components_importable(self):
        """Test that all components can be imported and used."""
        from src.master_debugger.orchestrator_v5 import MasterDebuggerV5
        from src.python_debug.debug_report import execute_with_debug
        from src.test_generator import TestGenerator
        from src.pyprover.contract_verifier import ContractVerifier
        from src.troubleshooting.phases_5 import Troubleshooter
        from src.code_orchestrator.orchestrator import CodeOrchestrator
        
        # All should import without error
        assert MasterDebuggerV5 is not None
        assert execute_with_debug is not None
        assert TestGenerator is not None
        assert ContractVerifier is not None
        assert Troubleshooter is not None
        assert CodeOrchestrator is not None
    
    @pytest.mark.integration
    def test_orchestrator_invokes_subcomponents(self):
        """Test that orchestrator properly invokes all subcomponents."""
        from src.master_debugger.orchestrator_v5 import MasterDebuggerV5, RiskLevel
        
        code = """
import socket
password = getpass.getpass()
"""
        
        debugger = MasterDebuggerV5()
        
        # Classify as critical
        risk = debugger.classify_risk(code)
        assert risk == RiskLevel.CRITICAL
        
        # Should invoke multiple phases
        report = debugger.debug(code)
        assert len(report.phases_executed) >= 2
        assert report.total_issues is not None
