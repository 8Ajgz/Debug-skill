"""Master Debugger v5.0 - Full 4-phase orchestrator"""
from typing import List
from .types import RiskLevel, UnifiedReport
from .phases import (
    Phase0StaticAnalysis,
    Phase1RuntimeDebug,
    Phase2FormalVerification,
    Phase3DesignReview
)

class MasterDebuggerV5:
    """Master Debugger v5.0 - Automated 4-phase debugging orchestrator"""
    
    def classify_risk(self, code: str) -> RiskLevel:
        """Classify code risk level based on domain and complexity"""
        risk_indicators = {
            'RiskLevel.CRITICAL': [
                'cryptography', 'hashlib', 'password', 'encrypt', 'decrypt',
                'socket', 'requests', 'authenticate', 'authorize',
                'eval(', 'exec(', 'os.system', 'subprocess', 'pickle.loads',
                '.write(', 'delete', 'chmod',
            ],
            'RiskLevel.HIGH': [
                'open(', 'for ', 'while ', 'recursion', 'def ', 'class ',
                'state', 'transaction', 'order', 'payment',
                'complex', 'algorithm', 'binary_search'
            ],
            'RiskLevel.MEDIUM': ['def ', 'print', 'return', 'lambda']
        }
        
        code_lower = code.lower()
        
        # Check for CRITICAL indicators (security/credential/network sensitive)
        for indicator in risk_indicators['RiskLevel.CRITICAL']:
            if indicator in code_lower:
                return RiskLevel.CRITICAL
        
        # 'open(' for plain file I/O is HIGH on its own (resource lifecycle risk),
        # independent of the complexity check below.
        if 'open(' in code_lower:
            return RiskLevel.HIGH
        
        # Check for HIGH indicators
        for indicator in risk_indicators['RiskLevel.HIGH']:
            if indicator in code_lower:
                # Count complexity markers
                complexity = code.count('\n') / max(1, len(code.split('\n')))
                if complexity > 0.5 or code.count('if ') > 2:
                    return RiskLevel.HIGH
        
        return RiskLevel.MEDIUM
    
    def select_phases(self, risk: RiskLevel) -> List[int]:
        """Select which phases to execute based on risk level"""
        phase_map = {
            RiskLevel.CRITICAL: [0, 1, 2, 3],  # All phases
            RiskLevel.HIGH: [0, 1, 2],         # Skip Phase 3 (design)
            RiskLevel.MEDIUM: [0, 1],          # Only static + runtime
            RiskLevel.LOW: [0],                # Static only
        }
        return phase_map[risk]
    
    def debug(self, code: str) -> UnifiedReport:
        """Execute full debugging workflow"""
        report = UnifiedReport(code=code, risk_level=self.classify_risk(code))
        phases_to_run = self.select_phases(report.risk_level)
        
        # Phase 0: Static Analysis
        if 0 in phases_to_run:
            report.phase_0_static = Phase0StaticAnalysis.run(code)
            report.phases_executed.append(0)
        
        # Phase 1: Runtime Debug
        if 1 in phases_to_run:
            report.phase_1_runtime = Phase1RuntimeDebug.run(code)
            report.phases_executed.append(1)
        
        # Phase 2: Formal Verification
        if 2 in phases_to_run:
            report.phase_2_formal = Phase2FormalVerification.run(code)
            report.phases_executed.append(2)
        
        # Phase 3: Design Review
        if 3 in phases_to_run:
            report.phase_3_design = Phase3DesignReview.run(code)
            report.phases_executed.append(3)
        
        # Calculate unified metrics
        self._calculate_metrics(report)
        
        return report
    
    def _calculate_metrics(self, report: UnifiedReport) -> None:
        """Calculate unified report metrics"""
        issues = 0
        passed_phases = 0
        
        if report.phase_0_static:
            issues += len(report.phase_0_static.mypy_errors)
            issues += len(report.phase_0_static.pylint_issues)
            if report.phase_0_static.passed:
                passed_phases += 1
        
        if report.phase_1_runtime:
            issues += len(report.phase_1_runtime.patterns_found)
            if report.phase_1_runtime.passed:
                passed_phases += 1
        
        if report.phase_2_formal:
            issues += report.phase_2_formal.contracts_failed
            if report.phase_2_formal.passed:
                passed_phases += 1
        
        if report.phase_3_design:
            if not report.phase_3_design.passed:
                issues += 1
            else:
                passed_phases += 1
        
        report.total_issues = issues
        
        # Confidence: percentage of phases that passed
        if report.phases_executed:
            report.confidence_score = passed_phases / len(report.phases_executed)
        
        # Generate summary
        risk_str = report.risk_level.value
        phases_str = f"{len(report.phases_executed)}/{4}"
        report.summary = (
            f"Risk: {risk_str} | Phases: {phases_str} | "
            f"Issues: {issues} | Confidence: {report.confidence_score:.1%}"
        )

# Public API
__all__ = ['MasterDebuggerV5']
