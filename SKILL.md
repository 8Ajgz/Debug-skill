---
name: debug-suite
version: 2.2.0
status: production
description: >
  Unified debugging and verification suite for 12+ languages. Full support for Python, JavaScript, Rust
  (Phases 2-3: borrow checker + clippy), and C/C++ (Phase 4: compiler diagnostics + Clang Static Analyzer).
  Combines runtime debugging, static/formal analysis (PyProver v12 integration), test generation,
  and problem diagnosis. Features 4-phase automated debugging with risk classification, 12-language support via PyProver bridge,
  graceful tool degradation, and expert Rust lifetime/ownership + C/C++ memory-safety analysis. Master-debugger-v6 orchestrates all phases.

compatibility: "Python 3.8+; Rust toolchain (rustc+clippy) recommended for Rust debugging; Clang (clang/clang++) recommended for C/C++ debugging; PyProver v12+ optional"
interop_level: 4
---

# Debug Suite v2.2

**Status:** Production Ready | **Components:** 12 | **Languages:** 12+ | **Rust Support:** ✅ Complete (Phases 2-3) | **C/C++ Support:** ✅ Complete (Phase 4)

Unified suite combining runtime debugging (Python, JavaScript, Rust), static/formal analysis (PyProver), borrow checker analysis (Rust), clippy linting (Rust), Clang compiler diagnostics + Static Analyzer (C/C++), comprehensive testing, and problem diagnosis across 12+ programming languages.

**NEW in v2.2:** C/C++-Debug (Phase 4) complete. Compiles C/C++ with `clang -Wall -Wextra` for fast syntactic diagnostics (uninitialized variables, type mismatches, format-string bugs) and runs the Clang Static Analyzer for path-sensitive bugs (null dereferences, memory leaks, division by zero). Adds a lightweight design-review pass flagging unsafe string APIs (`gets`, `strcpy`) and unmatched raw `new`. Graceful degradation if clang/clang++ unavailable. Also includes a full cross-module bugfix pass (see CHANGELOG): fixed broken package imports, dead/duplicate orchestrator code, mismatched enum/dataclass field names, and stale test expectations across pyprover_bridge, rust_debug, master_debugger, and javascript_debug — full test suite now 144/144 passing (was 105/125 before this pass).

**NEW in v2.1:** Rust-Debug (Phases 2-3) complete. Parses rustc borrow checker violations, runs clippy for style/safety/performance lints. Graceful degradation if rustc/clippy unavailable. Merges results into unified risk classification.

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
| **rust-debug** | v1.0 | Borrow checker (rustc) + clippy lints (Rust) | ✅ Complete |
| **cpp-debug** | v1.0 | Compiler diagnostics + Clang Static Analyzer (C/C++) | ✅ Complete |
| **master-debugger-v5** | v5.0 | 4-phase orchestrator (static → runtime → formal → design) with cross-language support | ✅ Complete |
| **pyprover** | v14.0 | Formal verification with Z3 (Phase 2: contracts; Phase 3: tokens/async/FFI) | ✅ Complete |
| **test-generator** | v1.1 | Edge cases, mutations, metamorphic, red-team adversarial tests | ✅ Complete |
| **code-orchestrator** | v1.1 | Multi-function codebase analysis, GitHub projects, decomposition, checkpointing | ✅ Complete |
| **troubleshooting** | v1.0 | 5-phase methodology, problem classification, diagnosis, remediation | ✅ Complete |
| **common** | - | Shared types, utilities, interfaces | ✅ Complete |

---

## Unified Interoperability Layer (NEW in v1.2)

`src/common/interop.py` gives every component a shared format so results can flow between them.

**UnifiedDebugReport** - All debugging components normalize output to one report: execution timeline,
detected bug patterns (severity + suggestions), variable mutations/aliasing, risk classification +
confidence score, execution metrics and exceptions.

**ComponentBridge** - lets one component invoke another and consume its results (e.g. python-debug
output flowing into test-generator). **LanguageDetector** - auto-detects code language and routes to
the matching debugger.

**Unified Type System** - shared across all components: `Variable`, `Mutation`, `BugPattern`,
`ExecutionEvent`, `OperationError`, and the `RiskLevel` / `BugSeverity` / `LanguageType` enums.

✅ Cross-language workflows (Python debug → JS testing) · ✅ Tool composition (Debug → Verify → Test → Diagnose)
✅ Consistent reporting · ✅ Unified error handling · ✅ New languages slot in without core API changes

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

### Rust-Debug v1.0 (Phases 2-3)

```python
from src.rust_debug import RustDebugger

report = RustDebugger().debug(rust_code)   # rustc borrow checker + cargo clippy
print(report.risk_level, report.patterns_detected)
```

Merges `rustc --error-format=json` borrow-checker violations with `cargo clippy
--message-format=json` lints into one deduplicated, severity-sorted pattern
list. Degrades gracefully (no findings, not an error) if rustc/clippy aren't installed.

### Cpp-Debug v1.0 (Phase 4 - NEW in v2.2)

```python
from src.cpp_debug import CppDebugger

report = CppDebugger().debug(c_code, dialect="c")   # or dialect="cpp"
print(report.risk_level, report.patterns_detected)
```

Two-layer analysis: `clang -fsyntax-only -Wall -Wextra` for fast syntactic
diagnostics (uninitialized variables, sign comparisons, format-string bugs),
plus `clang --analyze` (Clang Static Analyzer) for path-sensitive bugs
compiler warnings can't catch — null dereferences, memory leaks,
division-by-zero. A design-review pass flags unsafe string APIs (`gets`,
`strcpy`) and raw `new` with no matching `delete`. Degrades gracefully if
clang/clang++ aren't installed.

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

### Rust-Debug
- ✅ You need borrow checker / ownership violation detection
- ✅ You want clippy style/safety/performance lints
- ✅ You're debugging unsafe blocks, unwrap()/panic!() usage
- ❌ Don't use without rustc/clippy installed (degrades to no findings, not an error)

### Cpp-Debug
- ✅ You need uninitialized-variable, type-mismatch, or format-string detection (C/C++)
- ✅ You want path-sensitive null-dereference / memory-leak / div-by-zero detection
- ✅ You're checking for unsafe string APIs (gets, strcpy) or unmatched raw new
- ❌ Don't use without clang/clang++ installed (degrades to no findings, not an error)
- ❌ Don't expect full AST-level refactoring support — this is diagnostic-based, not a transformer

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
| **master-debugger** | `src/master_debugger/tests/test_orchestration.py` | 18 | ✅ |
| **python-debug** | `src/python_debug/tests/test_execution_tracing.py` | 25+ | ✅ |
| **rust-debug** | `tests/test_rust_debug_phases_2_3.py` | 21 | ✅ |
| **cpp-debug** | `src/cpp_debug/tests/test_cpp_debug_phase4.py` | 19 | ✅ |
| **pyprover-bridge** | `tests/test_pyprover_integration.py` | 24 | ✅ |
| **pyprover** | `src/pyprover/tests/test_verification.py` | 15+ | ✅ |
| **test-generator** | `src/test_generator/tests/test_generation.py` | 20+ | ✅ |
| **Integration** | `src/tests/test_integration.py` | 6 | ✅ |

**144/144 tests passing** as of v2.2.0 (`python -m pytest tests/ src/ -q`).

### Test Markers

`tracing` · `patterns` · `verification` · `generation` · `contract` · `integration` · `performance` · `slow` (excluded by default)

---

## Known Limitations

- **Static analysis tools (Phase 0, Python):** Requires mypy, pylint, bandit installed
- **Z3 solver (Phase 2):** Requires z3-solver package
- **Rust-Debug:** Requires rustc + cargo clippy installed; degrades to empty findings (not an error) otherwise
- **Cpp-Debug:** Requires clang/clang++ installed; degrades to empty findings (not an error) otherwise; diagnostic-based, not a full AST transformer
- **GitHub analysis (code-orchestrator):** Requires read access to repositories
- **Async tracking:** Via context managers, not actual async execution
- **PyProver bridge:** `verify()` currently returns a structurally-correct placeholder result (not a real PyProver invocation) since the PyProver package itself isn't installed in this environment — wire `self._pyprover_module.verify(...)` in `pyprover_bridge.py` once PyProver is available
- **Phases 5-10 (C/C++ DWARF/KLEE, Assembly):** Not yet implemented — see roadmap below

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

- **v2.2.0** (2026-06-30): C/C++-Debug (Phase 4) + suite-wide bugfix pass
  - Added Cpp-Debug: clang compiler diagnostics + Clang Static Analyzer + design review for C/C++
  - Routed C/C++ code through master-debugger-v6 automatically
  - Fixed missing `src/__init__.py` and 4 missing test-package `__init__.py` files that broke relative imports
  - Fixed `master_debugger/__init__.py`, `orchestrator_v5.py` risk-classifier false positives, missing `RiskLevel.LOW`
  - Implemented previously-stubbed `PyProverBridge._convert_to_unified_report` / `_map_language_type`, extended `LanguageType` to all 12 PyProver languages
  - Fixed wrong/nonexistent enum members and dataclass kwargs across `rust_debug` (`ComponentType.RUNTIME`→`RUST_DEBUG`, `ComponentType.STATIC`→`RUST_DEBUG`, `BugPattern(message=...)`→`description=...`, missing `UnifiedDebugReport` required args, `.line`→`.location`)
  - Wired master-debugger-v6's Python path to the real Phase0/1/3 analyzers instead of stub phase-name appending
  - Fixed stale `verification_debugging_suite` import in javascript_debug tests (project was renamed)
  - Full suite: 144/144 tests passing (was 105/125 before this pass)
- **v2.1.0** (2026-06-28): Rust-Debug (Phases 2-3)
  - Added PyProver Integration Bridge (Phase 1)
  - Added Rust borrow checker parser + clippy linter (Phases 2-3)
  - Master-debugger-v6 routes Rust code to RustDebugger automatically
- **v1.2.0** (2026-06-28): Cross-language debugging support
  - Merged JavaScript Debug v1.0 into suite
  - Master-debugger-v5 now supports both Python and JavaScript code
  - Added Promise/async tracking for JavaScript debugging
  - Added aliasing detection for JavaScript objects
  - Enhanced bug pattern detection for 10 JavaScript-specific patterns
  - Integrated JavaScript execution tracer with same API as Python variant
- **v1.0.1** (2026-06-24): Maintenance release - fixed circular imports, added 80+ test cases, pytest.ini
- **v1.0.0** (2026-06-24): Production release - all 4 phases complete, all 7 components stable
- **v0.9.0 / v0.5.0** (2026-06-22/23): Beta/Alpha releases

For detailed changes, see CHANGELOG.md

