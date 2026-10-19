"""Type definitions and dataclasses for code-orchestrator.

Provides all structured data types used throughout the orchestration system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple


class VerificationPhaseStatus(Enum):
    """Status of a verification phase."""
    INIT = "init"
    PLANNED = "planned"
    VERIFYING = "verifying"
    COMPLETE = "complete"
    PAUSED = "paused"
    INCOMPLETE = "incomplete"


class OperationErrorType(Enum):
    """Types of errors that can occur during orchestration."""
    PARSE_ERROR = "parse_error"
    DECOMPOSITION_ERROR = "decomposition_error"
    STATE_ERROR = "state_error"
    CHECKPOINT_ERROR = "checkpoint_error"
    COVERAGE_ERROR = "coverage_error"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    INVALID_CODE = "invalid_code"


@dataclass
class OperationError:
    """Structured error type for orchestration operations."""
    error_type: OperationErrorType
    message: str
    context: Dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        """Return human-readable error message."""
        return f"{self.error_type.value}: {self.message}"


@dataclass
class Function:
    """Represents a single function in the codebase."""
    name: str
    module: str
    lines_of_code: int
    complexity_score: float
    callees: List[str] = field(default_factory=list)  # Functions this calls
    callers: List[str] = field(default_factory=list)  # Functions that call this
    is_testable: bool = True
    is_verifiable: bool = True
    docstring: Optional[str] = None
    
    def __hash__(self) -> int:
        """Make Function hashable."""
        return hash((self.name, self.module))


@dataclass
class CodeStructure:
    """Analysis of code structure."""
    functions: List[Function]
    call_graph: Dict[str, List[str]]  # name → [called functions]
    dependency_graph: Dict[str, List[str]]  # name → [depends on]
    modules: Dict[str, List[str]]  # module_name → [function names]
    total_lines: int
    analyzable_percentage: float
    language: str = "python"

    def function_by_name(self, name: str) -> Optional[Function]:
        """Get function by name."""
        for func in self.functions:
            if func.name == name:
                return func
        return None


@dataclass
class VerificationPhase:
    """A phase of verification targeting specific functions."""
    phase_number: int
    target_functions: List[str]
    estimated_tokens: int
    reason: str  # e.g., "leaf functions, no dependencies"
    preconditions: List[str] = field(default_factory=list)  # e.g., ["phase_1_verified"]
    complexity_level: str = "moderate"  # "simple", "moderate", "complex"


@dataclass
class DecompositionPlan:
    """Plan for decomposing code into verification phases."""
    phases: List[VerificationPhase]
    total_functions: int
    total_lines: int
    estimated_total_tokens: int
    strategy: str  # "topological_sort", "leaf_first", etc.
    coverage_target: str = "100% of analyzable code"


@dataclass
class FunctionResult:
    """Result of verifying a single function."""
    function_name: str
    verified: bool
    tools_run: Dict[str, dict] = field(default_factory=dict)  # {"python-debug": {...}, "pyprover": {...}}
    status: str = "pending"  # "verified", "failed", "pending", "blocked"
    failure_reason: Optional[str] = None
    dependencies_verified: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class VerificationState:
    """Complete verification state (can be serialized/deserialized)."""
    project_id: str  # UUID for codebase
    codebase_hash: str  # Detect code changes
    
    # Structure
    code_structure: Optional[CodeStructure] = None
    decomposition_plan: Optional[DecompositionPlan] = None
    
    # Progress tracking
    verified_functions: Dict[str, FunctionResult] = field(default_factory=dict)
    pending_functions: List[str] = field(default_factory=list)
    failed_functions: Dict[str, str] = field(default_factory=dict)  # {function_name: reason}
    blocked_functions: List[str] = field(default_factory=list)
    
    # Coverage metrics
    functions_verified: int = 0
    functions_total: int = 0
    lines_verified: int = 0
    lines_total: int = 0
    
    # Token tracking
    tokens_spent: int = 0
    tokens_budget: int = 5000
    
    # Tool-specific tracking
    tools_run: Dict[str, List[str]] = field(default_factory=dict)  # {"pyprover": [funcs], "python-debug": [funcs]}
    
    # Current phase
    current_phase: int = 0
    phase_status: VerificationPhaseStatus = VerificationPhaseStatus.INIT
    
    # Session history
    prompts_used: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    verification_log: List[str] = field(default_factory=list)

    def add_verified_function(self, name: str, result: FunctionResult) -> None:
        """Register a verified function."""
        self.verified_functions[name] = result
        self.functions_verified += 1
        if name in self.pending_functions:
            self.pending_functions.remove(name)
        self.last_updated = datetime.now()

    def mark_phase_complete(self, phase: int) -> None:
        """Mark a phase as complete."""
        self.phase_status = VerificationPhaseStatus.COMPLETE
        self.last_updated = datetime.now()

    def get_blocked_functions(self) -> List[str]:
        """Get functions blocked by unverified dependencies."""
        return self.blocked_functions.copy()

    def get_next_unverified(self, phase: int) -> List[str]:
        """Get unverified functions for a phase."""
        if not self.decomposition_plan or phase >= len(self.decomposition_plan.phases):
            return []
        phase_funcs = self.decomposition_plan.phases[phase].target_functions
        return [f for f in phase_funcs if f not in self.verified_functions]

    def is_complete(self) -> bool:
        """Check if verification is complete."""
        return self.functions_verified >= self.functions_total and self.functions_total > 0

    def get_coverage_percentage(self) -> float:
        """Get percentage of code verified."""
        if self.functions_total == 0:
            return 0.0
        return (self.functions_verified / self.functions_total) * 100


@dataclass
class ToolCoverage:
    """Coverage metrics for a specific tool."""
    tool_name: str
    functions_analyzed: int
    functions_total: int
    percentage: float


@dataclass
class CoverageReport:
    """Unified coverage report across all tools."""
    functions_verified: int
    functions_total: int
    functions_percentage: float
    
    lines_verified: int
    lines_total: int
    lines_percentage: float
    
    dependency_completeness: float  # % of deps for verified functions also verified
    
    by_tool: Dict[str, ToolCoverage] = field(default_factory=dict)
    
    pending_functions: List[str] = field(default_factory=list)
    failed_functions: Dict[str, str] = field(default_factory=dict)
    blocked_functions: List[str] = field(default_factory=list)
    
    estimated_tokens_to_complete: int = 0
    tokens_remaining: int = 0
    
    next_high_value_functions: List[str] = field(default_factory=list)


@dataclass
class ToolRecommendation:
    """Recommendation for which tool to run next."""
    recommended_tool: str  # "pyprover", "python-debug", "test-generator", "master-debugger"
    reason: str
    target_functions: List[str] = field(default_factory=list)
    estimated_token_cost: int = 0
    expected_benefit: str = ""
    priority: int = 3  # 1 (high) to 5 (low)
