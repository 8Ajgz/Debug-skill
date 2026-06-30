"""
Unified Interoperability Layer for Debug Suite v1.2

Enables seamless communication between Python debugging, JavaScript debugging, formal
verification, test generation, and other components. Standardizes execution reporting,
error handling, and result exchange across all skill components.

Design principles:
- Single unified report format across all languages and tools
- Standard error/exception handling contract
- Common type system for debugging artifacts (variables, mutations, patterns)
- Bidirectional tool invocation (Python → JS, JS → Python, etc.)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import json


class ComponentType(Enum):
    """Identifies which component produced a result."""
    PYTHON_DEBUG = "python-debug"
    JAVASCRIPT_DEBUG = "javascript-debug"
    RUST_DEBUG = "rust-debug"
    CPP_DEBUG = "cpp-debug"
    PYPROVER = "pyprover"
    TEST_GENERATOR = "test-generator"
    CODE_ORCHESTRATOR = "code-orchestrator"
    TROUBLESHOOTING = "troubleshooting"
    MASTER_DEBUGGER = "master-debugger-v6"


class RiskLevel(Enum):
    """Unified risk classification across all components."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class BugSeverity(Enum):
    """Unified bug severity across all components."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class LanguageType(Enum):
    """Supported languages across suite.

    Covers the 3 languages with full debug-suite support (Python, JavaScript,
    Rust) plus all languages reachable via the PyProver formal-verification
    bridge (12 languages total; NASM and FASM both map to ASSEMBLY).
    """
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CPP = "cpp"
    C = "c"
    RUST = "rust"
    GO = "go"
    CSHARP = "csharp"
    WASM = "webassembly"
    ASSEMBLY = "assembly"


@dataclass
class Variable:
    """Unified representation of a variable across languages."""
    name: str
    type_name: str
    value: Any
    line: int
    scope: str = "global"
    is_mutable: bool = True
    references: List[str] = field(default_factory=list)  # Other vars this aliases


@dataclass
class Mutation:
    """Unified representation of a variable mutation."""
    variable: str
    old_value: Any
    new_value: Any
    line: int
    timestamp: float
    source: str = ""  # e.g., "assignment", "method_call", "property_access"


@dataclass
class BugPattern:
    """Unified representation of a detected bug pattern."""
    pattern_type: str  # e.g., "NULL_REFERENCE", "ALIASING_MUTATION"
    severity: BugSeverity
    location: str  # "line 42", "function foo()"
    description: str
    component: ComponentType
    language: LanguageType
    suggestion: str = ""
    confidence: float = 1.0  # 0-1, how confident we are in this detection


@dataclass
class ExecutionEvent:
    """Unified execution timeline event."""
    timestamp: float
    event_type: str  # "assignment", "call", "return", "exception", "promise_resolved"
    line: int
    detail: str
    variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedDebugReport:
    """
    Unified report format produced by ANY debugging component.
    
    Works across Python Debug, JavaScript Debug, and future language debuggers.
    All components normalize their output to this format.
    """
    component: ComponentType
    language: LanguageType
    code: str
    
    # Execution results
    timeline: List[ExecutionEvent] = field(default_factory=list)
    final_state: Dict[str, Variable] = field(default_factory=dict)
    mutations: List[Mutation] = field(default_factory=list)
    
    # Analysis results
    patterns_detected: List[BugPattern] = field(default_factory=list)
    aliased_variables: List[List[str]] = field(default_factory=list)  # Groups of aliases
    
    # Metadata
    execution_time_ms: float = 0.0
    total_events: int = 0
    exceptions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Risk assessment
    risk_level: RiskLevel = RiskLevel.LOW
    confidence_score: float = 0.0  # 0-1
    summary: str = ""
    
    def to_dict(self) -> Dict:
        """Convert to dict for JSON serialization."""
        return {
            "component": self.component.value,
            "language": self.language.value,
            "risk_level": self.risk_level.value,
            "patterns_detected": len(self.patterns_detected),
            "timeline_events": len(self.timeline),
            "execution_time_ms": self.execution_time_ms,
            "aliases_found": len(self.aliased_variables)
        }
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())
    
    def merge_with(self, other: "UnifiedDebugReport") -> "UnifiedDebugReport":
        """
        Merge with another debug report (e.g., Python analysis + formal verification).
        Creates unified view of all detected issues.
        """
        merged_patterns = self.patterns_detected + other.patterns_detected
        merged_mutations = self.mutations + other.mutations
        
        # Combine aliases, deduplicating
        all_aliases = self.aliased_variables + other.aliased_variables
        unique_aliases = []
        for alias_group in all_aliases:
            if alias_group not in unique_aliases:
                unique_aliases.append(alias_group)
        
        return UnifiedDebugReport(
            component=ComponentType.MASTER_DEBUGGER,
            language=self.language,
            code=self.code,
            timeline=self.timeline,  # Use primary timeline
            final_state={**self.final_state, **other.final_state},
            mutations=merged_mutations,
            patterns_detected=merged_patterns,
            aliased_variables=unique_aliases,
            execution_time_ms=self.execution_time_ms + other.execution_time_ms,
            risk_level=max(self.risk_level, other.risk_level, 
                          key=lambda x: ["LOW", "MEDIUM", "HIGH", "CRITICAL"].index(x.value)),
        )


@dataclass
class OperationError:
    """Unified error/exception across all components."""
    error_type: str
    message: str
    component: ComponentType
    line: int = -1
    traceback: str = ""
    suggestions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "type": self.error_type,
            "message": self.message,
            "component": self.component.value,
            "line": self.line
        }


class ComponentBridge:
    """
    Enables one component to invoke another and consume results.
    
    Example:
        bridge = ComponentBridge()
        
        # Python debug finds issue
        py_report = python_debug.execute_with_debug(code)
        
        # Pass to test generator
        tests = bridge.invoke_component(
            source=ComponentType.PYTHON_DEBUG,
            target=ComponentType.TEST_GENERATOR,
            input_report=py_report
        )
    """
    
    def __init__(self):
        self.component_registry: Dict[ComponentType, Any] = {}
        self.result_cache: Dict[str, UnifiedDebugReport] = {}
    
    def register_component(self, component_type: ComponentType, instance: Any):
        """Register a component instance for invocation."""
        self.component_registry[component_type] = instance
    
    def invoke_component(
        self,
        source: ComponentType,
        target: ComponentType,
        input_report: UnifiedDebugReport
    ) -> UnifiedDebugReport:
        """
        Invoke target component with results from source component.
        Handles format translation and error handling.
        """
        if target not in self.component_registry:
            raise OperationError(
                error_type="ComponentNotFound",
                message=f"{target.value} not registered",
                component=ComponentType.MASTER_DEBUGGER
            )
        
        target_component = self.component_registry[target]
        
        # Route to appropriate handler
        if target == ComponentType.TEST_GENERATOR:
            return self._invoke_test_generator(target_component, input_report)
        elif target == ComponentType.PYPROVER:
            return self._invoke_pyprover(target_component, input_report)
        else:
            raise OperationError(
                error_type="UnsupportedRoute",
                message=f"No route from {source.value} to {target.value}",
                component=ComponentType.MASTER_DEBUGGER
            )
    
    def _invoke_test_generator(self, generator, report: UnifiedDebugReport) -> UnifiedDebugReport:
        """Route debug report to test generator."""
        # Test generator analyzes patterns and code to create tests
        # Returns enhanced report with test metadata
        pass
    
    def _invoke_pyprover(self, verifier, report: UnifiedDebugReport) -> UnifiedDebugReport:
        """Route debug report to formal verifier."""
        # Verifier analyzes patterns and creates contracts
        # Returns enhanced report with verification results
        pass


class LanguageDetector:
    """Auto-detect code language and route to appropriate debugger."""
    
    @staticmethod
    def detect_language(code: str) -> LanguageType:
        """Detect code language from source."""
        code_lower = code.strip().lower()
        
        # JavaScript/TypeScript indicators
        if any(x in code for x in ["const ", "let ", "var ", "async ", "await ", "Promise"]):
            if "interface " in code or "type " in code or ": string" in code:
                return LanguageType.TYPESCRIPT
            return LanguageType.JAVASCRIPT
        
        # Python indicators
        if any(x in code for x in ["def ", "import ", "class ", "async def", "@"]):
            return LanguageType.PYTHON
        
        # Default to Python
        return LanguageType.PYTHON
    
    @staticmethod
    def get_debugger_for_language(language: LanguageType):
        """Return appropriate debugger class for language."""
        if language == LanguageType.JAVASCRIPT:
            from verification_debugging_suite.javascript_debug import JavaScriptDebugger
            return JavaScriptDebugger
        elif language == LanguageType.PYTHON:
            from verification_debugging_suite.python_debug import execute_with_debug
            return execute_with_debug
        else:
            raise ValueError(f"No debugger for {language.value}")


__all__ = [
    "ComponentType",
    "RiskLevel",
    "BugSeverity",
    "LanguageType",
    "Variable",
    "Mutation",
    "BugPattern",
    "ExecutionEvent",
    "UnifiedDebugReport",
    "OperationError",
    "ComponentBridge",
    "LanguageDetector",
]
