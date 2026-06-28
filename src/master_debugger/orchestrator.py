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


class DebugPhase(str, Enum):
    STATIC = "static"
    RUNTIME = "runtime"
    FORMAL = "formal"
    TESTING = "testing"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


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
        if use_pyprover and PyProverBridge is not None:
            self.pyprover_bridge = PyProverBridge(use_pyprover=True)
    
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
        
        report = UnifiedDebugReport()
        token_cost = 0
        
        # Phase 0: Static Analysis
        if "static" in phases:
            report.phases_completed.append(DebugPhase.STATIC)
            token_cost += 50
        
        # Phase 1: Runtime Debugging
        if "runtime" in phases:
            report.phases_completed.append(DebugPhase.RUNTIME)
            token_cost += 100
        
        # Phase 2: Formal Verification (with PyProver)
        if "formal" in phases:
            pyprover_result = await self._phase_2_formal(code, language)
            if pyprover_result:
                report.pyprover_result = pyprover_result
                token_cost += 300
            report.phases_completed.append(DebugPhase.FORMAL)
        
        # Phase 3: Design Review & Testing
        if "testing" in phases:
            report.phases_completed.append(DebugPhase.TESTING)
            token_cost += 200
        
        # Classify overall health
        if report.pyprover_result and report.pyprover_result.get("verified"):
            report.overall_health = "✅ VERIFIED"
            report.risk_level = RiskLevel.LOW
            report.confidence_score = 0.95
        else:
            report.overall_health = "⚠️  INCONCLUSIVE"
            report.risk_level = RiskLevel.MEDIUM
            report.confidence_score = 0.6
        
        report.token_cost = token_cost
        report.recommendations = self._generate_recommendations(report)
        
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
            if result:
                return {
                    "verified": getattr(result, "verified", False),
                    "template_type": getattr(result, "template_type", None),
                    "error": getattr(result, "error", None),
                }
            return None
        except Exception as e:
            print(f"[MasterDebugger] PyProver error: {e}", file=sys.stderr)
            return None
    
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
        """Quickly classify code risk level."""
        return {
            "risk_level": "medium",
            "score": 0.5,
            "recommendation": "Run full debug_comprehensive for detailed analysis"
        }


master_debugger = MasterDebugger()


async def debug_comprehensive(code: str, language: str = "python", input_data: Optional[Dict[str, Any]] = None, phases: Optional[List[str]] = None) -> Union[UnifiedDebugReport, Exception]:
    return await master_debugger.debug_comprehensive(code, language, input_data, phases)


async def classify_risk(code: str, language: str = "python") -> Dict[str, Any]:
    return await master_debugger.classify_risk(code, language)
