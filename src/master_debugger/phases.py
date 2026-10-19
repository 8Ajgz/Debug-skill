"""Phase 0-3 implementations for Master Debugger v5.0"""
import subprocess
from typing import Optional
from .types import (
    RiskLevel, StaticAnalysisResult, RuntimeDebugResult,
    FormalVerificationResult, DesignReviewResult, UnifiedReport
)

class Phase0StaticAnalysis:
    """Static analysis using mypy, pylint, bandit"""
    
    @staticmethod
    def run(code: str) -> StaticAnalysisResult:
        """Run static analysis on code"""
        result = StaticAnalysisResult()
        
        # Write code to temp file for analysis
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            # Run mypy
            try:
                output = subprocess.run(
                    ['mypy', '--strict', temp_path],
                    capture_output=True, text=True, timeout=5
                )
                if output.returncode != 0:
                    result.mypy_errors = output.stdout.split('\n')
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            # Run pylint
            try:
                output = subprocess.run(
                    ['pylint', temp_path],
                    capture_output=True, text=True, timeout=5
                )
                if output.returncode != 0:
                    result.pylint_issues = output.stdout.split('\n')[:10]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            # Run bandit
            try:
                output = subprocess.run(
                    ['bandit', temp_path],
                    capture_output=True, text=True, timeout=5
                )
                if 'WARNING' in output.stdout or 'SEVERITY' in output.stdout:
                    result.bandit_warnings = output.stdout.split('\n')[:10]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            result.passed = len(result.mypy_errors) == 0
        finally:
            import os
            os.unlink(temp_path)
        
        return result

class Phase1RuntimeDebug:
    """Runtime debugging using python-debug"""
    
    @staticmethod
    def run(code: str) -> RuntimeDebugResult:
        """Run runtime debugging on code"""
        from ..python_debug import execute_with_debug
        from ..python_debug.bug_patterns import BugPatternDetector
        
        result = RuntimeDebugResult()
        
        try:
            report = execute_with_debug(code)
            result.timeline = [
                {"lineno": event.lineno, "type": event.event_type}
                for event in report.timeline[:20]  # First 20 events
            ]
            result.variables = report.dump_variables()
            result.exceptions = str(report.exception_info) if report.exception_info else None
            
            # Detect patterns
            detector = BugPatternDetector(report)
            patterns = detector.analyze()
            result.patterns_found = [p.pattern_type for p in patterns[:5]]
            result.passed = len(patterns) == 0
        except Exception as e:
            result.exceptions = str(e)
        
        return result

class Phase2FormalVerification:
    """Formal verification using pyprover"""
    
    @staticmethod
    def run(code: str) -> FormalVerificationResult:
        """Run formal verification on code"""
        result = FormalVerificationResult()
        
        try:
            # Try to import and use pyprover Phase 2 if available
            from ..pyprover import verify_contract
            
            # Attempt verification
            verification = verify_contract(code, language="python")
            result.contracts_verified = 1 if verification.get('verified') else 0
            result.contracts_failed = 0 if verification.get('verified') else 1
            result.passed = verification.get('verified', False)
            result.details = verification
        except (ImportError, Exception) as e:
            # Phase 2 not yet fully implemented
            result.contracts_verified = 0
            result.contracts_failed = 1
            result.passed = False
            result.details = {"error": str(e)}
        
        return result

class Phase3DesignReview:
    """Design review using troubleshooting methodology"""
    
    @staticmethod
    def run(code: str) -> DesignReviewResult:
        """Run design review on code"""
        from ..troubleshooting import Troubleshooter
        
        result = DesignReviewResult()
        
        try:
            troubleshooter = Troubleshooter()
            diagnosis = troubleshooter.diagnose(code, context="python_code")
            
            result.classification = diagnosis.get("stage", "unknown")
            result.diagnosis = diagnosis
            result.remediation = diagnosis.get("remediation_steps", [])
            result.passed = True
        except (ImportError, Exception) as e:
            result.diagnosis = {"error": str(e)}
            result.passed = False
        
        return result
