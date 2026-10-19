"""Type definitions for Master Debugger v5.0"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

# RiskLevel used to be redefined here with lowercase values ("critical", "high",
# ...), a separate class from common.interop.RiskLevel (uppercase values,
# "CRITICAL", "HIGH", ...) used by every per-language debugger (RustDebugger,
# CppDebugger, CDebugger, AssemblyDebugger). Both printed identically as
# "RiskLevel.CRITICAL" but were different classes, so `==` silently failed
# across them - e.g. `report.risk_level == RiskLevel.CRITICAL` was False for
# any report from a per-language debugger even when genuinely critical, if
# the RiskLevel on the comparing side came from this module (as it did via
# the top-level src/__init__.py's `from src.master_debugger.orchestrator_v5
# import RiskLevel`). Unified onto common.interop.RiskLevel, which is what
# every UnifiedDebugReport-based component already used, so this is now the
# only RiskLevel definition MasterDebuggerV5's pipeline touches. See
# CHANGELOG.md and roadmap.md §11.6 for the full history of this bug.
from ..common.interop import RiskLevel

@dataclass
class StaticAnalysisResult:
    mypy_errors: List[str] = field(default_factory=list)
    pylint_issues: List[str] = field(default_factory=list)
    bandit_warnings: List[str] = field(default_factory=list)
    semgrep_findings: List[str] = field(default_factory=list)
    # A tool that ran and failed (timeout, crash, unparseable output). A tool
    # that is not installed is a skip and is not recorded here.
    tool_errors: List[str] = field(default_factory=list)
    passed: bool = False
    
@dataclass
class RuntimeDebugResult:
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    variables: Dict[str, List[Any]] = field(default_factory=dict)
    exceptions: Optional[str] = None
    patterns_found: List[str] = field(default_factory=list)
    passed: bool = False

@dataclass
class FormalVerificationResult:
    contracts_verified: int = 0
    contracts_failed: int = 0
    loop_invariants_verified: int = 0
    passed: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DesignReviewResult:
    classification: str = "unknown"
    diagnosis: Dict[str, Any] = field(default_factory=dict)
    remediation: List[str] = field(default_factory=list)
    passed: bool = False

@dataclass
class UnifiedReport:
    code: str
    risk_level: RiskLevel
    phase_0_static: StaticAnalysisResult = field(default_factory=StaticAnalysisResult)
    phase_1_runtime: RuntimeDebugResult = field(default_factory=RuntimeDebugResult)
    phase_2_formal: Optional[FormalVerificationResult] = None
    phase_3_design: Optional[DesignReviewResult] = None
    phases_executed: List[int] = field(default_factory=list)
    total_issues: int = 0
    confidence_score: float = 0.0
    summary: str = ""
