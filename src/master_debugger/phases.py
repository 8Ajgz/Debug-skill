"""Phase 0-3 implementations for Master Debugger v5.0"""
import json
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
            except subprocess.TimeoutExpired:
                result.tool_errors.append("mypy: timed out after 5s")
            except FileNotFoundError:
                pass  # not installed: a skip, not a failure
            
            # Run pylint
            try:
                output = subprocess.run(
                    ['pylint', temp_path],
                    capture_output=True, text=True, timeout=5
                )
                if output.returncode != 0:
                    result.pylint_issues = output.stdout.split('\n')[:10]
            except subprocess.TimeoutExpired:
                result.tool_errors.append("pylint: timed out after 5s")
            except FileNotFoundError:
                pass  # not installed: a skip, not a failure
            
            # Run bandit
            #
            # NOTE (v2.6.0): this used to check
            # `'WARNING' in output.stdout or 'SEVERITY' in output.stdout`
            # against bandit's default human-readable text output, which
            # never matches - real bandit output says "Severity:" (mixed
            # case) and "Issue:", never the all-caps strings this checked
            # for. So this silently reported zero bandit findings on every
            # single input, indistinguishable from "ran bandit, found
            # nothing" - a real security-relevant silent-failure bug, same
            # class as the CBMC 6.x flag issue documented in roadmap.md
            # §11.9. Never caught because bandit was never installed in
            # whatever environment last exercised this code path (the
            # FileNotFoundError except silently swallows the "not
            # installed" case identically to "installed but found
            # nothing"). Fixed by using `-f json` for structured, stable
            # parsing instead of matching against human-readable text.
            try:
                output = subprocess.run(
                    ['bandit', '-f', 'json', temp_path],
                    capture_output=True, text=True, timeout=5
                )
                try:
                    bandit_data = json.loads(output.stdout)
                    result.bandit_warnings = [
                        f"[{r['test_id']}] {r['issue_severity']}: {r['issue_text']} "
                        f"(line {r['line_number']})"
                        for r in bandit_data.get('results', [])
                    ][:10]
                except (json.JSONDecodeError, KeyError) as e:
                    # bandit exits 1 when it finds issues but still writes JSON,
                    # so unparseable stdout means the tool itself failed.
                    result.tool_errors.append(
                        f"bandit: unparseable output (exit {output.returncode}): {type(e).__name__}"
                    )
            except subprocess.TimeoutExpired:
                result.tool_errors.append("bandit: timed out after 5s")
            except FileNotFoundError:
                pass  # not installed: a skip, not a failure

            # Run semgrep (v2.6.0) - pattern-based second opinion alongside
            # bandit, using a locally-bundled rule subset since semgrep.dev's
            # registry isn't reachable from sandboxed environments. See
            # common/semgrep_analyzer.py and common/semgrep_rules/README.md.
            try:
                from ..common.semgrep_analyzer import SemgrepAnalyzer
                semgrep_patterns = SemgrepAnalyzer(timeout=12).analyze(code, language="python")
                result.semgrep_findings = [
                    f"[{p.pattern_type}] {p.severity.value}: {p.description} ({p.location})"
                    for p in semgrep_patterns
                ][:10]
            except Exception as e:
                result.tool_errors.append(f"semgrep: {type(e).__name__}: {e}")

            # A phase only passes if every tool that ran also completed.
            result.passed = len(result.mypy_errors) == 0 and not result.tool_errors
        finally:
            import os
            os.unlink(temp_path)
        
        return result

class Phase1RuntimeDebug:
    """Runtime debugging using python-debug"""
    
    @staticmethod
    def run(code: str) -> RuntimeDebugResult:
        """Run runtime debugging on code"""
        try:
            from ..python_debug import execute_with_debug
            from ..python_debug.bug_patterns import BugPatternDetector
        except ImportError:
            from python_debug import execute_with_debug  # type: ignore[no-redef]
            from python_debug.bug_patterns import BugPatternDetector  # type: ignore[no-redef]

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
            try:
                from ..pyprover import verify_contract
            except ImportError:
                from pyprover import verify_contract  # type: ignore[no-redef]
            
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
        try:
            from ..troubleshooting import Troubleshooter
        except ImportError:
            from troubleshooting import Troubleshooter  # type: ignore[no-redef]

        result = DesignReviewResult()

        try:
            troubleshooter = Troubleshooter()
            diagnosis = troubleshooter.diagnose(code, context="python_code")
            # diagnosis is a DiagnosisResult dataclass — use field access, not .get()
            result.classification = diagnosis.classified_stage
            result.diagnosis = {
                "stage": diagnosis.classified_stage,
                "causes": diagnosis.possible_causes,
                "evidence": diagnosis.phase_0_evidence,
            }
            result.remediation = diagnosis.remediation_steps
            result.passed = diagnosis.verification_passed
        except (ImportError, Exception) as e:
            result.diagnosis = {"error": str(e)}
            result.passed = False
        
        return result
