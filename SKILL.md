---
name: verification-debugging-suite
version: 1.0.0
status: production
description: >
  Unified verification and debugging orchestrator combining formal verification (pyprover v14.0),
  runtime debugging (python-debug v12.3), test generation (test-generator v1.1), and automated
  problem diagnosis (troubleshooting v1.0). Use this suite for comprehensive code verification,
  automated debugging with risk classification (CRITICAL/HIGH/MEDIUM), contract verification,
  test generation, and problem diagnosis. Master-debugger-v5 orchestrates all phases automatically.
  
  **Key capabilities:**
  - 4-phase automated debugging (static analysis → runtime → formal verification → design review)
  - Formal contract verification with Z3 SMT solver
  - Comprehensive test generation with mutation testing and red-team adversarial tests
  - Systematic codebase analysis and GitHub project verification
  - Universal 5-phase troubleshooting methodology
  - All 7 components work together or standalone

compatibility: "Python 3.8+ with z3-solver>=4.12, hypothesis>=6.0, pytest>=7.0"
interop_level: 3
---

# Verification-Debugging-Suite v1.0

**Status:** Production Ready | **Components:** 7 | **Total Capability:** ~22,000 lines of implementation

Unified suite combining Python verification, debugging, testing, and problem diagnosis tools.

---

## Quick Start (5 minutes)

### Use Case 1: Debug critical code automatically

```python
from verification_debugging_suite import MasterDebuggerV5

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
from verification_debugging_suite.test_generator import TestGenerator

generator = TestGenerator()
code = "def add(a, b): return a + b"

tests = generator.generate_tests(code, language="python")
print(f"Generated {len(tests)} test cases")
print(f"Coverage: {tests.coverage_percent}%")
```

### Use Case 3: Verify formal contracts

```python
from verification_debugging_suite.pyprover import ContractVerifier

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
from verification_debugging_suite.troubleshooting import Troubleshooter

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
| **python-debug** | v12.3 | Runtime execution tracing, variable state, bug pattern detection | ✅ Complete |
| **master-debugger-v5** | v5.0 | 4-phase orchestrator (static → runtime → formal → design) | ✅ Complete |
| **pyprover** | v14.0 | Formal verification with Z3 (Phase 2: contracts; Phase 3: tokens/async/FFI) | ✅ Complete |
| **test-generator** | v1.1 | Edge cases, mutations, metamorphic, red-team adversarial tests | ✅ Complete |
| **code-orchestrator** | v1.1 | Multi-function codebase analysis, GitHub projects, decomposition, checkpointing | ✅ Complete |
| **troubleshooting** | v1.0 | 5-phase methodology, problem classification, diagnosis, remediation | ✅ Complete |
| **common** | - | Shared types, utilities, interfaces | ✅ Complete |

---

## Full API Reference

### Master Debugger v5.0

```python
from verification_debugging_suite import MasterDebuggerV5, RiskLevel, UnifiedReport

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
from verification_debugging_suite.python_debug import execute_with_debug
from verification_debugging_suite.python_debug.bug_patterns import BugPatternDetector

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

### PyProver v14.0

```python
from verification_debugging_suite.pyprover import ContractVerifier, verify_contract

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
from verification_debugging_suite.test_generator import TestGenerator

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
from verification_debugging_suite.code_orchestrator import CodeOrchestrator

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
from verification_debugging_suite.troubleshooting import Troubleshooter

troubleshooter = Troubleshooter()

# Diagnose problem
diagnosis = troubleshooter.diagnose(problem_description, context="code")

print(f"Stage: {diagnosis.classified_stage}")       # input/processing/output
print(f"Causes: {diagnosis.possible_causes}")       # Root causes
print(f"Solutions: {diagnosis.remediation_steps}")  # Fix steps
print(f"Verified: {diagnosis.verification_passed}")
```

---

## When to Use Each Component

### Master-Debugger-v5
- ✅ You want automated phase selection (skip manual tool choice)
- ✅ You need comprehensive 4-phase debugging
- ✅ You care about code risk classification
- ✅ You want one unified report
- ❌ Don't use if you need fine-grained phase control (use individual skills)

### Python-Debug
- ✅ You need runtime execution trace
- ✅ You want to see variable mutations
- ✅ You need aliasing detection
- ✅ You want bug pattern detection
- ❌ Don't use for static analysis (use pyprover Phase 2)

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

## Workflow Examples

### Example 1: Debug & Fix Function

```python
from verification_debugging_suite import MasterDebuggerV5
from verification_debugging_suite.test_generator import TestGenerator

# Step 1: Debug with master-debugger-v5
debugger = MasterDebuggerV5()
code = """
def calculate_discount(price, discount_percent):
    return price * (100 - discount_percent) / 100
"""
report = debugger.debug(code)

# Step 2: Generate tests to verify fix
generator = TestGenerator()
tests = generator.generate_tests(code)

# Step 3: Run tests
for test in tests.test_cases:
    print(f"Test: {test.input} → {test.expected}")
```

### Example 2: Verify GitHub Project

```python
from verification_debugging_suite.code_orchestrator import CodeOrchestrator

orchestrator = CodeOrchestrator()

# Clone and analyze
analysis = orchestrator.analyze_github("https://github.com/user/repo")

# Get verification plan
plan = orchestrator.decompose(analysis)

# Check coverage
print(f"Functions to verify: {len(plan.functions)}")
print(f"Estimated time: {plan.estimated_hours} hours")
print(f"Token budget: {plan.token_estimate}")

# Verify (across multiple prompts)
for checkpoint in orchestrator.checkpoints():
    # Each checkpoint: verify batch of functions
    results = orchestrator.run_checkpoint(checkpoint)
    print(f"Verified {results.count} functions")
```

### Example 3: Diagnose & Troubleshoot

```python
from verification_debugging_suite.troubleshooting import Troubleshooter

troubleshooter = Troubleshooter()

# Get error message
error = """
TypeError: 'NoneType' object is not subscriptable
  File "app.py", line 42, in process
    result = data[0]
"""

# Diagnose
diagnosis = troubleshooter.diagnose(error, context="python")

print(f"Stage: {diagnosis.classified_stage}")       # processing
print(f"Root cause: {diagnosis.possible_causes}")    # [None value, missing validation]
print(f"Fix: {diagnosis.remediation_steps}")         # [Add None check, validate input]
```

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

- **v1.0.0** (2026-06-24): Production release - all 4 phases complete, all 7 components stable
- **v0.9.0** (2026-06-23): Beta release - components integrated, documentation added
- **v0.5.0** (2026-06-22): Alpha release - core implementations present

For detailed changes, see CHANGELOG.md

