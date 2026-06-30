"""Type definitions for Master Debugger v5.0"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum

class RiskLevel(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class StaticAnalysisResult:
    mypy_errors: List[str] = field(default_factory=list)
    pylint_issues: List[str] = field(default_factory=list)
    bandit_warnings: List[str] = field(default_factory=list)
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
