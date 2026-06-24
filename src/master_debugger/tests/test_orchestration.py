"""
Tests for Master Debugger v5.0 orchestrator.

Tests the 4-phase debugging workflow, risk classification,
and orchestration of all verification tools.
"""

import pytest
from ..orchestrator_v5 import MasterDebuggerV5, RiskLevel
from ..types import UnifiedReport


class TestRiskClassification:
    """Test risk classification accuracy."""
    
    @pytest.fixture
    def debugger(self):
        return MasterDebuggerV5()
    
    @pytest.mark.parametrize("code,expected_risk", [
        # Cryptographic operations -> CRITICAL
        ("from cryptography import Fernet", RiskLevel.CRITICAL),
        ("import hashlib; x = hashlib.sha256()", RiskLevel.CRITICAL),
        ("password = input('Enter password')", RiskLevel.CRITICAL),
        
        # Network operations -> CRITICAL
        ("import socket; s = socket.socket()", RiskLevel.CRITICAL),
        ("import requests; requests.get('http://api.example.com')", RiskLevel.CRITICAL),
        
        # File I/O -> HIGH
        ("f = open('file.txt', 'r')", RiskLevel.HIGH),
        ("with open('secret.key') as f: data = f.read()", RiskLevel.HIGH),
        
        # Algorithms/complexity -> HIGH
        ("for i in range(100):\n    for j in range(100):\n        x = i * j", RiskLevel.HIGH),
        
        # Simple code -> MEDIUM
        ("x = 1", RiskLevel.MEDIUM),
        ("def hello(): return 'world'", RiskLevel.MEDIUM),
    ])
    def test_classification_accuracy(self, debugger, code, expected_risk):
        """Test that code is classified to correct risk level."""
        risk = debugger.classify_risk(code)
        assert risk == expected_risk, \
            f"Code classified as {risk}, expected {expected_risk}\nCode:\n{code}"
    
    def test_classification_returns_valid_level(self, debugger):
        """Test that classification always returns valid RiskLevel."""
        test_codes = [
            "x = 1",
            "import os",
            "def foo(): pass",
            "if True: x = 1",
        ]
        
        for code in test_codes:
            risk = debugger.classify_risk(code)
            assert risk in [RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM]


class TestPhaseSelection:
    """Test that appropriate phases are selected based on risk."""
    
    @pytest.fixture
    def debugger(self):
        return MasterDebuggerV5()
    
    @pytest.mark.parametrize("risk,expected_phases", [
        (RiskLevel.CRITICAL, [0, 1, 2, 3]),  # All phases
        (RiskLevel.HIGH, [0, 1, 2]),  # Phase 0-2
        (RiskLevel.MEDIUM, [0, 1]),  # Phase 0-1
    ])
    def test_phase_selection(self, debugger, risk, expected_phases):
        """Test that phases are selected correctly based on risk."""
        phases = debugger.select_phases(risk)
        assert phases == expected_phases, \
            f"Risk {risk} selected phases {phases}, expected {expected_phases}"


class TestUnifiedReporting:
    """Test unified report generation."""
    
    @pytest.fixture
    def debugger(self):
        return MasterDebuggerV5()
    
    def test_report_structure(self, debugger):
        """Test that reports have expected structure."""
        code = "x = 1"
        report = debugger.debug(code)
        
        assert isinstance(report, UnifiedReport)
        assert report.risk_level is not None
        assert report.phases_executed is not None
        assert report.total_issues is not None
        assert report.confidence_score is not None
        assert report.summary is not None
    
    def test_report_summary_content(self, debugger):
        """Test that report summary contains expected information."""
        code = "x = 1 / 0"
        report = debugger.debug(code)
        
        summary = report.summary
        assert "Risk:" in summary
        assert "Phases:" in summary
        assert "Issues:" in summary
        assert "Confidence:" in summary


class TestOrchestrationWorkflow:
    """Test complete 4-phase orchestration."""
    
    @pytest.fixture
    def debugger(self):
        return MasterDebuggerV5()
    
    @pytest.mark.integration
    def test_critical_code_workflow(self, debugger):
        """Test full workflow on critical code."""
        code = """
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(('localhost', 8080))
data = s.recv(1024)
s.close()
"""
        
        report = debugger.debug(code)
        
        # Should run all phases for CRITICAL code
        assert report.risk_level == RiskLevel.CRITICAL
        assert len(report.phases_executed) >= 3
        assert report.phases_executed[0] == 0  # Phase 0 always runs
    
    @pytest.mark.integration
    def test_simple_code_workflow(self, debugger):
        """Test workflow on simple code."""
        code = "x = 1 + 1"
        
        report = debugger.debug(code)
        
        # Should be minimal phases for simple code
        assert report.risk_level in [RiskLevel.MEDIUM, RiskLevel.LOW]
        assert len(report.phases_executed) >= 1
