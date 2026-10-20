# Verification-Debugging-Suite API Reference

**Hand-maintained; not generated from source. Keep in sync with openapi.yaml and INTEROP.yaml. For usage examples, see SKILL.md.**

---

## Table of Contents

1. [Master-Debugger-v5](#master-debugger-v5)
2. [Python-Debug](#python-debug)
3. [PyProver](#pyprover)
4. [Test-Generator](#test-generator)
5. [Code-Orchestrator](#code-orchestrator)
6. [Troubleshooting](#troubleshooting)

---

## Master-Debugger-v5

**Module:** `verification_debugging_suite.master_debugger_v5`

### Functions

#### `MasterDebuggerV5.classify_risk(code: str) -> RiskLevel`

Classify code risk level (CRITICAL, HIGH, MEDIUM) based on code patterns.

**Parameters:**
- `code` (str) – Python code to classify

**Returns:**
- `RiskLevel` – Risk classification enum

**Example:**
```python
from verification_debugging_suite import MasterDebuggerV5
debugger = MasterDebuggerV5()
risk = debugger.classify_risk("def divide(a, b): return a / b")
```

#### `MasterDebuggerV5.debug(code: str) -> UnifiedReport`

Execute full 4-phase debugging workflow on code.

**Parameters:**
- `code` (str) – Python code to debug

**Returns:**
- `UnifiedReport` – Comprehensive debugging report with all phases

**Report Fields:**
- `risk_level: RiskLevel` – Risk classification
- `phases_executed: List[int]` – Phases that ran [0, 1, 2, 3]
- `total_issues: int` – Total issues found across all phases
- `confidence_score: float` – Confidence level (0–1)
- `summary: str` – Human-readable summary
- `phase_0_static: StaticAnalysisResult` – Static analysis output
- `phase_1_runtime: RuntimeDebugResult` – Runtime debugging output
- `phase_2_formal: FormalVerificationResult` – Formal verification output (if CRITICAL/HIGH)
- `phase_3_design: DesignReviewResult` – Design review output (if CRITICAL)

---

## Python-Debug

**Module:** `verification_debugging_suite.python_debug`

### Functions

#### `execute_with_debug(code: str, **kwargs) -> DebugReport`

Execute Python code with full execution tracing.

**Parameters:**
- `code` (str) – Python code to execute
- `kwargs` – Additional tracing options

**Returns:**
- `DebugReport` – Execution trace with timeline and final state

**Report Fields:**
- `timeline: List[DebugEvent]` – Execution events in order
- `final_state: Dict[str, Any]` – Final variable values
- `execution_time_ms: float` – Total execution time

### Classes

#### `BugPatternDetector(report: DebugReport)`

Detect common bug patterns in execution trace.

**Methods:**
- `analyze() -> List[BugPattern]` – Detect patterns in trace
  - Returns patterns with type, severity, line number

**Pattern Types:**
- `null_dereference` – Access to None values
- `type_mismatch` – Unexpected type operations
- `off_by_one` – Loop boundary errors
- `aliasing_mutation` – Unintended object sharing
- `infinite_loop` – Non-terminating loops

---

## PyProver

**Module:** `verification_debugging_suite.pyprover`

### Functions

#### `verify_contract(code: str, language: str = "python") -> Dict[str, Any]`

Verify formal contract (precondition, postcondition, invariant).

**Parameters:**
- `code` (str) – Code with contract comments (# Pre: ..., # Post: ...)
- `language` (str) – Language (currently "python" only)

**Returns:**
- `Dict` with fields:
  - `verified: bool` – Contract holds
  - `details: str` – Verification details
  - `counterexample: Optional[str]` – Counterexample if not verified

### Classes

#### `ContractVerifier`

Main verification interface.

**Methods:**
- `parse_contract(code: str) -> Contract` – Parse contract from comments
- `verify_contract(code: str, contract: Contract) -> Dict` – Verify contract

---

## Test-Generator

**Module:** `verification_debugging_suite.test_generator`

### Functions

#### `TestGenerator.generate_tests(code: str, language: str = "python") -> TestSuite`

Generate comprehensive test suite for function.

**Parameters:**
- `code` (str) – Function code to test
- `language` (str) – Language ("python" or "javascript")

**Returns:**
- `TestSuite` with:
  - `test_cases: List[TestCase]` – Generated test cases
  - `coverage_percent: float` – Code coverage (0–100)
  - `mutation_score: float` – Mutation score (0–1)

**Test Categories:**
- `edge_case` – Boundary values
- `metamorphic` – Relationship-based tests
- `adversarial` – Red-team tests
- `mutation` – Tests that catch common mutations

---

## Code-Orchestrator

**Module:** `verification_debugging_suite.code_orchestrator`

### Classes

#### `CodeOrchestrator`

Manage multi-function codebase verification.

**Methods:**
- `analyze_project(path: str) -> CodeAnalysis` – Analyze codebase structure
- `analyze_github(url: str) -> CodeAnalysis` – Clone and analyze GitHub repo
- `decompose(analysis: CodeAnalysis) -> VerificationPlan` – Create verification plan
- `recommend_tool(function: Function) -> str` – Recommend verification tool
- `checkpoint() -> CheckpointState` – Save verification progress
- `restore(checkpoint: CheckpointState)` – Resume from checkpoint

---

## Troubleshooting

**Module:** `verification_debugging_suite.troubleshooting`

### Classes

#### `Troubleshooter`

5-phase problem diagnosis.

**Methods:**
- `diagnose(problem: str, context: str = "code") -> DiagnosisResult` – Diagnose problem

**DiagnosisResult Fields:**
- `classified_stage: str` – Problem stage (input/processing/output)
- `possible_causes: List[str]` – Root cause hypotheses
- `remediation_steps: List[str]` – Fix steps
- `verification_passed: bool` – Diagnosis verified

---

## Type Definitions

See `verification_debugging_suite.types` module for all type definitions:

- `RiskLevel` – Enum: CRITICAL, HIGH, MEDIUM
- `UnifiedReport` – Dataclass: Master-debugger output
- `DebugReport` – Dataclass: Python-debug output
- `TestSuite` – Dataclass: Test-generator output
- `DiagnosisResult` – Dataclass: Troubleshooter output
- `CodeAnalysis` – Dataclass: Code-orchestrator analysis

---

## Error Handling

All operations return structured errors (not exceptions):

```python
from verification_debugging_suite.types import OperationError

result = some_operation()
if isinstance(result, OperationError):
    print(f"Error: {result.message}")
    print(f"Details: {result.details}")
else:
    # Success
    print(result)
```

---

**Generated:** 2026-06-24 | **Version:** 2.9.6
