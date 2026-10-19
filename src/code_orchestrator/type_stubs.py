"""Type stubs for Code-Orchestrator compatibility."""

from typing import Optional, List, Any, Dict
from dataclasses import dataclass

@dataclass
class CodeStructure:
    name: str
    type: str
    metrics: Dict[str, Any]

@dataclass  
class Function:
    name: str
    lines: int
    complexity: int

@dataclass
class OperationError:
    error_type: str
    message: str
    
class OperationErrorType:
    RUNTIME_ERROR = "runtime_error"

@dataclass
class DecompositionPlan:
    functions: List[Function]
    order: List[str]

@dataclass
class VerificationPhase:
    name: str
    
@dataclass
class CoverageReport:
    coverage: float
    lines_covered: int
    total_lines: int

@dataclass
class VerificationState:
    phase: str
    status: str
    functions_verified: int = 0
    functions_total: int = 0
    lines_verified: int = 0
    lines_total: int = 0

@dataclass
class ToolRecommendation:
    tool: str
    reason: str

@dataclass
class ToolCoverage:
    tool: str
    coverage: float
    
@dataclass
class CoverageTracker:
    total_coverage: float = 0.0

@dataclass
class DecompositionPlanner:
    pass

@dataclass
class VerificationStateIO:
    pass

@dataclass
class ReportGenerator:
    pass

@dataclass
class VerificationStateMachine:
    pass

@dataclass
class ToolRecommender:
    pass

@dataclass
class GitHubProjectAnalyzer:
    pass

@dataclass
class MultiFileAnalyzer:
    pass

@dataclass
class TestTargetExtractor:
    pass

@dataclass
class GitHubProject:
    name: str

@dataclass
class ProjectStructure:
    files: List[str]

# Make type stubs available as module-level items
__all__ = [
    "CodeStructure",
    "Function", 
    "OperationError",
    "OperationErrorType",
    "DecompositionPlan",
    "VerificationPhase",
    "CoverageReport",
    "VerificationState",
    "ToolRecommendation",
    "ToolCoverage",
    "CoverageTracker",
    "DecompositionPlanner",
    "VerificationStateIO",
    "ReportGenerator",
    "VerificationStateMachine",
    "ToolRecommender",
    "GitHubProjectAnalyzer",
    "MultiFileAnalyzer",
    "TestTargetExtractor",
    "GitHubProject",
    "ProjectStructure"
]
