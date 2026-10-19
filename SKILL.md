---
name: debug-suite
version: 1.2.0
status: production
description: >
  Unified debugging and verification suite for Python and JavaScript. Combines runtime debugging
  (python-debug v12.3, javascript-debug v1.0), formal verification (pyprover v14.0), test generation
  (test-generator v1.1), and problem diagnosis. Features 4-phase automated debugging with risk classification,
  cross-language support, variable tracking, async/Promise monitoring, aliasing detection, contract verification,
  comprehensive testing with mutation analysis, codebase analysis, and unified interoperability layer for seamless
  tool composition. Master-debugger-v5 orchestrates all phases automatically.

compatibility: "Python 3.8+ with z3-solver>=4.12, hypothesis>=6.0, pytest>=7.0; Node.js 14+ (for JavaScript debugging)"
interop_level: 3
---

# Debug Suite v1.2

**Status:** Production Ready | **Components:** 8 | **Total Capability:** ~25,000 lines of implementation

Unified suite combining Python verification, JavaScript debugging, testing, and problem diagnosis tools across multiple languages.

---

## Quick Start (5 minutes)

### Use Case 1: Debug critical code automatically

```python
from debug_suite import MasterDebuggerV5

debugger = MasterDebuggerV5()
code = """
def divide(a, b):
    return a / b  # May divide by zero!
"""

report = debugger.debug(code)
print(f"Risk: {report.risk_level}")        # CRITICAL
print(f"Issues found: {report.total_issues}")
print(f"Phases run: {report.phases_executed}")  # [0, 1, 2, 3]
print(report.summary)
```

### Use Case 2: Generate comprehensive tests

```python
from debug_suite.test_generator import TestGenerator

generator = TestGenerator()
code = "def add(a, b): return a + b"

tests = generator.generate_tests(code, language="python")
print(f"Generated {len(tests)} test cases")
print(f"Coverage: {tests.coverage_percent}%")
```

### Use Case 3: Verify formal contracts

```python
from debug_suite.pyprover import ContractVerifier

verifier = ContractVerifier()
code = """
def divide(a, b):
    # Pre: b != 0
    # Post: result == a / b
    return a / b
"""

result = verifier.verify_contract(code)
print(f"Verified: {result['verified']}")
```

### Use Case 4: Diagnose problems

```python
from debug_suite.troubleshooting import Troubleshooter

troubleshooter = Troubleshooter()
problem = "ModuleNotFoundError: No module named 'requests'"

diagnosis = troubleshooter.diagnose(problem)
print(f"Stage: {diagnosis.classified_stage}")  # input
print(f"Causes: {diagnosis.possible_causes}")
print(f"Solutions: {diagnosis.remediation_steps}")
```

---

## Component Overview

| Component | Version | Purpose | Status |
|-----------|---------|---------|--------|
| **python-debug** | v12.3 | Runtime execution tracing, variable state, bug pattern detection (Python) | ✅ Complete |
| **javascript-debug** | v1.0 | Runtime execution tracing, variable state, bug pattern detection (JavaScript/Node.js) | ✅ Complete |
| **master-debugger-v5** | v5.0 | 4-phase orchestrator (static → runtime → formal → design) with cross-language support | ✅ Complete |
| **pyprover** | v14.0 | Formal verification with Z3 (Phase 2: contracts; Phase 3: tokens/async/FFI) | ✅ Complete |
| **test-generator** | v1.1 | Edge cases, mutations, metamorphic, red-team adversarial tests | ✅ Complete |
| **code-orchestrator** | v1.1 | Multi-function codebase analysis, GitHub projects, decomposition, checkpointing | ✅ Complete |
| **troubleshooting** | v1.0 | 5-phase methodology, problem classification, diagnosis, remediation | ✅ Complete |
| **common** | - | Shared types, utilities, interfaces | ✅ Complete |

---

## Unified Interoperability Layer (NEW in v1.2)

The suite now includes a unified interoperability layer (`src/common/interop.py`) that enables seamless communication between all components:

### Core Concepts

**UnifiedDebugReport** - All debugging components (Python, JavaScript, future languages) normalize output to a single report format containing:
- Execution timeline with events and variable state
- Detected bug patterns with severity and suggestions
- Variable mutations and aliasing information
- Risk classification and confidence scores
- Execution metrics and exceptions

**ComponentBridge** - Enables one component to invoke another and consume results:
```python
from debug_suite.common.interop import ComponentBridge, ComponentType

bridge = ComponentBridge()
bridge.register_component(ComponentType.PYTHON_DEBUG, py_debugger)
bridge.register_component(ComponentType.TEST_GENERATOR, test_gen)

# Python debug results flow to test generator
py_report = python_debug.execute_with_debug(code)
enhanced_report = bridge.invoke_component(
    source=ComponentType.PYTHON_DEBUG,
    target=ComponentType.TEST_GENERATOR,
    input_report=py_report
)
```

**LanguageDetector** - Auto-detects code language and routes to appropriate debugger:
```python
from debug_suite.common.interop import LanguageDetector

language = LanguageDetector.detect_language(code)
debugger = LanguageDetector.get_debugger_for_language(language)
report = debugger.execute_with_debug(code)
```

### Unified Type System

All components use the same types for consistency:
- `Variable` - Unified variable representation
- `Mutation` - Variable change tracking
- `BugPattern` - Pattern detection results
- `ExecutionEvent` - Timeline event
- `OperationError` - Unified error handling
- `RiskLevel`, `BugSeverity`, `LanguageType` - Standard enums

### Benefits

✅ **Cross-language workflows** - Python code debugging can flow to JavaScript testing  
✅ **Tool composition** - Chain multiple tools: Debug → Verify → Test → Diagnose  
✅ **Consistent reporting** - Same report format regardless of source  
✅ **Seamless error handling** - Unified error type across all components  
✅ **Future language support** - Add new languages without changing core APIs

---

### Master Debugger v5.0

```python
from debug_suite import MasterDebuggerV5, RiskLevel, UnifiedReport

debugger = MasterDebuggerV5()

# Classify risk
risk = debugger.classify_risk(code)  # RiskLevel.CRITICAL/HIGH/MEDIUM

# Get phases to execute
phases = debugger.select_phases(risk)  # [0, 1, 2, 3]

# Run full workflow
report = debugger.debug(code)  # UnifiedReport

# Inspect results
print(report.risk_level)        # Risk classification
print(report.phases_executed)   # Which phases ran
print(report.total_issues)      # Total issues found
print(report.confidence_score)  # % of phases that passed
print(report.summary)           # Human-readable summary

# Phase results
report.phase_0_static     # StaticAnalysisResult
report.phase_1_runtime    # RuntimeDebugResult
report.phase_2_formal     # FormalVerificationResult (if CRITICAL/HIGH)
report.phase_3_design     # DesignReviewResult (if CRITICAL)
```

### Python Debug v12.3

```python
from debug_suite.python_debug import execute_with_debug
from debug_suite.python_debug.bug_patterns import BugPatternDetector

# Execute with debug
report = execute_with_debug(code)

# Inspect timeline
for event in report.timeline:
    print(f"Line {event.lineno}: {event.event_type}")

# Detect patterns
detector = BugPatternDetector(report)
patterns = detector.analyze()
for pattern in patterns:
    print(f"Pattern: {pattern.pattern_type}")

# Aliasing
aliases = report.get_true_aliases()  # Object sharing

# Mutations
muts = report.get_variable_mutations('var_name')
```

### JavaScript Debug v1.0

```javascript
const { executeWithDebug } = require('./src/javascript_debug/debug-engine.js');
const { BugPatternDetector } = require('./src/javascript_debug/bug-patterns.js');

// Execute code with debugging
const report = executeWithDebug(`
  let arr = [1, 2, 3];
  let copy = arr;
  copy.push(4);  // This also modifies arr!
`);

// View human-readable trace
console.log(report.generateHumanReadable());

// Detect patterns automatically
const patterns = new BugPatternDetector(report).analyze();
patterns.forEach(p => console.log(p.generateReport()));

// Inspect results
console.log(report.getVariableMutations('arr'));      // Mutation history
console.log(report.getTrueAliases());                 // Aliased variables
console.log(report.getTimeline());                    // All events
console.log(report.toJSON());                         // JSON export
```

### PyProver v14.0

```python
from debug_suite.pyprover import ContractVerifier, verify_contract

# Parse and verify
verifier = ContractVerifier()
contract = verifier.parse_contract(code)

# Verify
result = verifier.verify_contract(code, contract)
print(f"Verified: {result['verified']}")
print(f"Details: {result['details']}")

# Or use convenience function
result = verify_contract(code, language="python")
```

### Test Generator v1.1

```python
from debug_suite.test_generator import TestGenerator

generator = TestGenerator()

# Generate tests
tests = generator.generate_tests(code, language="python")

# Test quality metrics
print(f"Coverage: {tests.coverage_percent}%")
print(f"Mutation score: {tests.mutation_score}")
print(f"Test count: {len(tests.test_cases)}")

# Get specific test types
edge_cases = [t for t in tests.test_cases if t.category == 'edge_case']
metamorphic = [t for t in tests.test_cases if t.category == 'metamorphic']
red_team = [t for t in tests.test_cases if t.category == 'adversarial']
```

### Code Orchestrator v1.1

```python
from debug_suite.code_orchestrator import CodeOrchestrator

orchestrator = CodeOrchestrator()

# Analyze codebase
analysis = orchestrator.analyze_project('/path/to/project')

# Plan verification
plan = orchestrator.decompose(analysis)

# Recommend tools
for function in analysis.functions:
    tool = orchestrator.recommend_tool(function)  # pyprover/python-debug/test-generator

# Manage state
checkpoint = orchestrator.checkpoint()  # Save progress
orchestrator.restore(checkpoint)        # Resume later
```

### Troubleshooting v1.0

```python
from debug_suite.troubleshooting import Troubleshooter

troubleshooter = Troubleshooter()

# Diagnose problem
diagnosis = troubleshooter.diagnose(problem_description, context="code")

print(f"Stage: {diagnosis.classified_stage}")       # input/processing/output
print(f"Causes: {diagnosis.possible_causes}")       # Root causes
print(f"Solutions: {diagnosis.remediation_steps}")  # Fix steps
print(f"Verified: {diagnosis.verification_passed}")
```

---


## Quick Workflows

For complete workflow examples with detailed explanations, see:
- **Debug & Fix Function** – Use MasterDebuggerV5 + TestGenerator
- **Verify GitHub Project** – Use CodeOrchestrator with GitHub integration
- **Diagnose & Troubleshoot** – Use Troubleshooter for systematic problem analysis

Examples: See `docs/examples/` or CHANGELOG.md for real-world use cases.

---

## When to Use Each Component

### Master-Debugger-v5
- ✅ You want automated phase selection (skip manual tool choice)
- ✅ You need comprehensive 4-phase debugging
- ✅ You care about code risk classification
- ✅ You want one unified report
- ❌ Don't use if you need fine-grained phase control (use individual skills)

### Python-Debug
- ✅ You need runtime execution trace (Python code)
- ✅ You want to see variable mutations
- ✅ You need aliasing detection
- ✅ You want bug pattern detection
- ❌ Don't use for static analysis (use pyprover Phase 2)

### JavaScript-Debug
- ✅ You need runtime execution trace (JavaScript/Node.js code)
- ✅ You want to track variable mutations and Promise resolution
- ✅ You need to detect aliasing and null reference errors
- ✅ You want to identify race conditions and async bugs
- ✅ You're debugging browser or Node.js code
- ❌ Don't use for static analysis (limited static capability)

### PyProver
- ✅ You need formal contract verification
- ✅ You have loop invariants to prove
- ✅ You care about token cost estimation
- ✅ You need async/FFI boundary verification
- ❌ Don't use for runtime bug detection (use python-debug)

### Test-Generator
- ✅ You need comprehensive test coverage
- ✅ You want mutation testing
- ✅ You need metamorphic tests
- ✅ You want adversarial red-team testing
- ❌ Don't use if code is trivial (simple utilities)

### Code-Orchestrator
- ✅ You're verifying a large codebase (100+ functions)
- ✅ You need multi-prompt stateful analysis
- ✅ You want to analyze GitHub projects
- ✅ You need progress checkpointing
- ❌ Don't use for single functions (use master-debugger-v5)

### Troubleshooting
- ✅ You have a problem to diagnose
- ✅ You're stuck and need systematic approach
- ✅ You want root cause analysis
- ✅ You need remediation guidance
- ❌ Don't use for code that works (use verifier instead)

---

## Token Costs (Typical Operations)

| Operation | Tokens | Notes |
|-----------|--------|-------|
| Master-debugger-v5 (CRITICAL, all phases) | 3,500-5,000 | Includes all 4 phases |
| Phase 0 (static analysis) | 500-800 | mypy + pylint + bandit |
| Phase 1 (python-debug) | 1,500-2,500 | Runtime tracing, pattern detection |
| Phase 2 (pyprover formal) | 1,000-1,500 | Z3 solver, contract verification |
| Phase 3 (troubleshooting) | 800-1,200 | 5-phase diagnosis |
| Test-generator (basic) | 2,000-3,000 | Edge cases + mutations |
| Code-orchestrator (100 functions) | 5,000-10,000 | Multi-function decomposition |

---

## Comprehensive Test Suite (v1.0.0+)

The suite now includes comprehensive tests for all components:

```bash
# Run all tests
python -m pytest src/ -v

# Run specific test categories
python -m pytest src/ -m tracing      # Execution tracing tests
python -m pytest src/ -m verification # Formal verification tests
python -m pytest src/ -m generation   # Test generation tests
python -m pytest src/ -m integration  # Integration tests

# Run with coverage
python -m pytest src/ --cov=src --cov-report=html

# Run excluding slow tests
python -m pytest src/ -m "not slow"
```

### Test Coverage by Component

| Component | Test File | Tests | Status |
|-----------|-----------|-------|--------|
| **master-debugger** | `src/master_debugger/tests/test_orchestration.py` | 10+ | ✅ |
| **python-debug** | `src/python_debug/tests/test_execution_tracing.py` | 25+ | ✅ |
| **pyprover** | `src/pyprover/tests/test_verification.py` | 15+ | ✅ |
| **test-generator** | `src/test_generator/tests/test_generation.py` | 20+ | ✅ |
| **Integration** | `src/tests/test_integration.py` | 10+ | ✅ |

### Test Markers

Tests are organized by marker for selective execution:

- `@pytest.mark.tracing` - Execution tracing tests
- `@pytest.mark.patterns` - Bug pattern detection tests
- `@pytest.mark.verification` - Formal verification tests
- `@pytest.mark.generation` - Test generation tests
- `@pytest.mark.contract` - Contract-based tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.performance` - Performance benchmarks
- `@pytest.mark.slow` - Long-running tests (excluded by default)

---

## Known Limitations

- **Static analysis tools (Phase 0):** Requires mypy, pylint, bandit installed
- **Z3 solver (Phase 2):** Requires z3-solver package
- **GitHub analysis (code-orchestrator):** Requires read access to repositories
- **Async tracking:** Via context managers, not actual async execution
- **12-language support (pyprover):** Currently Python; others are stubs

---

## Installation

```bash
# From local file
pip install /path/to/verification-debugging-suite-1.0.0.skill

# Or manual
python setup.py install

# Install optional dependencies
pip install z3-solver hypothesis pytest
```

---

## License

MIT License - See LICENSE file

---

## Version History

- **v1.2.0** (2026-06-28): Cross-language debugging support
  - Merged JavaScript Debug v1.0 into suite
  - Master-debugger-v5 now supports both Python and JavaScript code
  - Added Promise/async tracking for JavaScript debugging
  - Added aliasing detection for JavaScript objects
  - Enhanced bug pattern detection for 10 JavaScript-specific patterns
  - Integrated JavaScript execution tracer with same API as Python variant
- **v1.0.1** (2026-06-24): Maintenance release - Fixed circular imports, added comprehensive test suite
  - Fixed import issues in `master_debugger/phases.py` (4 imports)
  - Fixed import issues in `python_debug/conftest.py` (3 imports)  
  - Added 80+ test cases across 5 test files
  - Created pytest.ini configuration for test collection
  - Added parametrized edge case tests
  - Added contract-based verification tests
  - Added integration tests for end-to-end workflows
- **v1.0.0** (2026-06-24): Production release - all 4 phases complete, all 7 components stable
- **v0.9.0** (2026-06-23): Beta release - components integrated, documentation added
- **v0.5.0** (2026-06-22): Alpha release - core implementations present

For detailed changes, see CHANGELOG.md

