"""
PyProver v14.0 Phase 3: Extended Type System
Token Profiling, Async Support, and FFI Verification
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union, Any, Tuple
from enum import Enum
import time


# ============================================================================
# PHASE 3A: TOKEN PROFILER TYPES
# ============================================================================

class OperationType(Enum):
    """Operation types for token cost estimation."""
    VERIFY = "verify"
    SIMPLIFY = "simplify"
    PROVE_INVARIANT = "prove_invariant"
    BATCH_VERIFY = "batch_verify"
    ASYNC_VERIFY = "async_verify"
    FFI_VERIFY = "ffi_verify"


@dataclass
class TokenCostFactors:
    """Token cost scaling factors for any operation."""
    baseline: int
    per_contract: int = 20
    per_file: int = 50
    per_invariant: int = 30
    language_multiplier: float = 1.0
    parallelism_overhead: int = 50
    async_overhead: int = 100
    ffi_overhead: int = 150


@dataclass
class TokenProfile:
    """Token usage profile for a verification operation."""
    operation: OperationType
    estimated_tokens: int
    actual_tokens: Optional[int] = None
    execution_time_seconds: float = 0.0
    contract_count: int = 0
    file_count: int = 1
    language: str = "python"
    has_async: bool = False
    has_ffi: bool = False
    
    def confidence_percent(self) -> int:
        """Confidence in estimate (0-100). Higher if actual tokens recorded."""
        if self.actual_tokens is not None:
            return 100
        if self.execution_time_seconds > 0:
            return 85
        return 70
    
    def efficiency_ratio(self) -> float:
        """Ratio of actual to estimated tokens (1.0 = perfect estimate)."""
        if self.actual_tokens is None:
            return None
        if self.estimated_tokens == 0:
            return float('inf')
        return self.actual_tokens / self.estimated_tokens


@dataclass
class TokenProfileReport:
    """Summary report of token usage across multiple operations."""
    operations: List[TokenProfile] = field(default_factory=list)
    total_estimated: int = 0
    total_actual: int = 0
    timestamp: float = field(default_factory=time.time)
    
    def add_operation(self, profile: TokenProfile) -> None:
        """Add an operation to the report."""
        self.operations.append(profile)
        self.total_estimated += profile.estimated_tokens
        if profile.actual_tokens:
            self.total_actual += profile.actual_tokens
    
    def average_efficiency(self) -> Optional[float]:
        """Average efficiency ratio across operations with actual tokens."""
        with_actuals = [op for op in self.operations if op.actual_tokens]
        if not with_actuals:
            return None
        return sum(op.efficiency_ratio() for op in with_actuals) / len(with_actuals)


# ============================================================================
# PHASE 3B: ASYNC VERIFICATION TYPES
# ============================================================================

class AsyncPattern(Enum):
    """Async patterns detected in code."""
    ASYNCIO_COROUTINE = "asyncio_coroutine"
    JAVASCRIPT_PROMISE = "javascript_promise"
    JAVASCRIPT_ASYNC_AWAIT = "javascript_async_await"
    RUST_ASYNC_FN = "rust_async_fn"
    RUST_FUTURE = "rust_future"
    PYTHON_ASYNC_FOR = "python_async_for"
    PYTHON_ASYNC_WITH = "python_async_with"


class ConcurrencyIssue(Enum):
    """Types of concurrency issues that can be detected."""
    RACE_CONDITION = "race_condition"
    DEADLOCK = "deadlock"
    DATA_RACE = "data_race"
    USE_AFTER_FREE_ASYNC = "use_after_free_async"
    LOST_UPDATE = "lost_update"
    ATOMICITY_VIOLATION = "atomicity_violation"


@dataclass
class AsyncFunction:
    """Metadata about an async function."""
    name: str
    language: str
    patterns: List[AsyncPattern]
    parameters: Dict[str, str]  # param_name -> type
    return_type: str
    is_generator: bool = False
    has_concurrent_access: bool = False
    concurrent_variables: List[str] = field(default_factory=list)
    
    def complexity_score(self) -> int:
        """0-100 score of async complexity."""
        score = 10  # Base
        score += len(self.patterns) * 15  # Each pattern adds complexity
        score += len(self.concurrent_variables) * 20  # Each concurrent var
        score += 30 if self.is_generator else 0
        return min(100, score)


@dataclass
class AsyncContract:
    """Contract for async function verification."""
    function_name: str
    requires: Optional[str] = None
    ensures: Optional[str] = None
    concurrent_requires: Optional[List[str]] = None  # Per-concurrent-var requirements
    
    # Async-specific constraints
    max_concurrent_calls: Optional[int] = None
    timeout_seconds: Optional[float] = None
    no_deadlock: bool = False
    no_race_condition: bool = False
    
    def to_z3_constraint(self) -> str:
        """Convert async contract to Z3 constraint expression."""
        constraints = []
        if self.requires:
            constraints.append(f"({self.requires})")
        if self.ensures:
            constraints.append(f"({self.ensures})")
        if self.no_deadlock:
            constraints.append("(no_deadlock)")
        if self.no_race_condition:
            constraints.append("(no_race_condition)")
        return " and ".join(constraints) if constraints else "true"


@dataclass
class AsyncVerificationResult:
    """Result of async function verification."""
    verified: bool
    function_name: str
    patterns_found: List[AsyncPattern]
    concurrency_issues: List[ConcurrencyIssue] = field(default_factory=list)
    proof: Optional[Dict[str, Any]] = None
    counterexample: Optional[Dict[str, Any]] = None
    time_seconds: float = 0.0
    complexity_score: int = 0


# ============================================================================
# PHASE 3C: FFI VERIFICATION TYPES
# ============================================================================

class FFILanguagePair(Enum):
    """Supported FFI boundary pairs."""
    PYTHON_TO_C = "python_c"
    PYTHON_TO_CPLUSPLUS = "python_cpp"
    RUST_TO_C = "rust_c"
    JAVASCRIPT_TO_WASM = "javascript_wasm"
    TYPESCRIPT_TO_WASM = "typescript_wasm"
    GO_TO_C = "go_c"
    JAVA_TO_JNI = "java_jni"


class FFITypeMapping(Enum):
    """Type coercion rules at FFI boundaries."""
    PYTHON_INT_TO_C_INT = "python_int -> c_int32"
    PYTHON_INT_TO_C_LONG = "python_int -> c_int64"
    PYTHON_FLOAT_TO_C_DOUBLE = "python_float -> c_double"
    PYTHON_BYTES_TO_C_PTR = "python_bytes -> c_ptr"
    PYTHON_LIST_TO_C_ARRAY = "python_list -> c_array"
    JS_NUMBER_TO_WASM_I32 = "js_number -> wasm_i32"
    JS_NUMBER_TO_WASM_F64 = "js_number -> wasm_f64"
    RUST_SLICE_TO_C_PTR_LEN = "rust_slice -> c_ptr_len"


class MemorySafetyIssue(Enum):
    """Memory safety issues at FFI boundaries."""
    NULL_POINTER_DEREFERENCE = "null_pointer"
    BUFFER_OVERFLOW = "buffer_overflow"
    USE_AFTER_FREE = "use_after_free"
    MEMORY_LEAK = "memory_leak"
    UNINITIALIZED_READ = "uninitialized_read"
    ALIGNMENT_MISMATCH = "alignment_mismatch"
    LIFETIME_VIOLATION = "lifetime_violation"


@dataclass
class FFISignature:
    """FFI function signature with type metadata."""
    library_name: str
    function_name: str
    language_pair: FFILanguagePair
    parameters: Dict[str, Tuple[str, str]]  # param_name -> (source_type, ffi_type)
    return_type: Tuple[str, str]  # (source_type, ffi_type)
    requires_pointer_validation: bool = False
    requires_lifetime_check: bool = False
    
    def type_mappings_used(self) -> List[FFITypeMapping]:
        """List all type mappings used in this signature."""
        mappings = []
        # Simplified: would need full mapping table in production
        return mappings


@dataclass
class FFIContract:
    """Contract for FFI boundary verification."""
    signature: FFISignature
    requires: Optional[str] = None  # Preconditions
    ensures: Optional[str] = None   # Postconditions
    no_null_pointers: bool = True
    no_buffer_overflow: bool = True
    valid_lifetime: bool = True
    memory_initialized: bool = True
    
    def to_z3_constraint(self) -> str:
        """Convert FFI contract to Z3 constraint expression."""
        constraints = []
        if self.requires:
            constraints.append(f"({self.requires})")
        if self.ensures:
            constraints.append(f"({self.ensures})")
        if self.no_null_pointers:
            constraints.append("(forall (p) (not (null p)))")
        if self.no_buffer_overflow:
            constraints.append("(forall (i) (<= i buffer_size))")
        return " and ".join(constraints) if constraints else "true"


@dataclass
class FFIVerificationResult:
    """Result of FFI boundary verification."""
    verified: bool
    signature: FFISignature
    type_safety: bool
    memory_safety: bool
    memory_issues: List[MemorySafetyIssue] = field(default_factory=list)
    proof: Optional[Dict[str, Any]] = None
    counterexample: Optional[Dict[str, Any]] = None
    time_seconds: float = 0.0
    
    def safety_score(self) -> int:
        """0-100 safety score."""
        score = 100
        score -= len(self.memory_issues) * 20
        score -= 0 if self.type_safety else 25
        score -= 0 if self.memory_safety else 30
        return max(0, score)


# ============================================================================
# UNIFIED RESULT TYPE
# ============================================================================

@dataclass
class Phase3Result:
    """Unified result type for Phase 3 operations."""
    operation_type: str  # "token_profile" | "async_verify" | "ffi_verify"
    success: bool
    
    # Token profiling
    token_profile: Optional[TokenProfile] = None
    
    # Async verification
    async_result: Optional[AsyncVerificationResult] = None
    
    # FFI verification
    ffi_result: Optional[FFIVerificationResult] = None
    
    # Error handling
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def estimate_async_overhead(pattern_count: int, var_count: int) -> int:
    """Estimate token overhead for async verification."""
    return 100 + (pattern_count * 50) + (var_count * 30)


def estimate_ffi_overhead(parameter_count: int, safety_checks: int) -> int:
    """Estimate token overhead for FFI verification."""
    return 150 + (parameter_count * 40) + (safety_checks * 20)


def language_complexity_multiplier(language: str) -> float:
    """Get complexity multiplier for a language (1.0-5.0)."""
    multipliers = {
        "python": 1.0,
        "javascript": 1.2,
        "typescript": 1.3,
        "go": 1.5,
        "java": 1.8,
        "rust": 2.0,
        "c": 2.2,
        "cpp": 2.5,
        "nasm": 3.0,
        "fasm": 3.0,
        "wasm": 2.0,
        "csharp": 1.6,
    }
    return multipliers.get(language.lower(), 1.5)
