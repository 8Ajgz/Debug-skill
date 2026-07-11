---
name: debug-suite
description: >
  Unified debugging and formal-verification suite for 12+ languages: Python/JavaScript runtime
  tracing and bug-pattern detection; Rust borrow-checker + clippy; C/C++ compiler diagnostics, Clang
  Static Analyzer, cppcheck, DWARF analysis, CBMC/KLEE symbolic execution; C strace + valgrind
  memcheck; Assembly disassembly, CFG, taint analysis, angr symbolic execution. Includes PyProver
  (Z3-backed contract/loop-invariant verification, code equivalence checking), automated test
  generation (metamorphic, mutation, red-team), codebase orchestration, and systematic
  problem-diagnosis. MasterDebugger auto-routes code by language through a 4-phase pipeline (static,
  runtime, formal, design) with risk classification and honest tool-availability reporting. Use
  whenever debugging, verifying, testing, or diagnosing code in these languages, whenever correctness
  (contracts, invariants, equivalence) needs proving rather than guessing, or a systematic root-cause
  methodology is needed for any broken system, not just code.

compatibility: "Python 3.8+; z3-solver for formal verification; Rust toolchain (rustc+clippy, or apt package rust-clippy) recommended for Rust; Clang and cppcheck recommended for C/C++; valgrind recommended for C dynamic memory-error detection; CBMC 6.x for symbolic execution (flag names changed from 5.x - see CHANGELOG 2.6.0); bandit and semgrep recommended for Python security analysis (semgrep uses a locally-bundled ruleset, not the semgrep.dev registry); lief recommended for C/C++ binary hardening analysis"

metadata:
  version: 2.9.6
  status: production
  interop_level: 4
---

# Debug Suite v2.9.6

**Status:** Production Ready | **Components:** 19 | **Test suite:** 482/482 (this sandbox, single `pytest` run covering both `src/` and the top-level `tests/` directory — see "NEW in v2.9.6" below; optional-tool skip count varies by environment — see CHANGELOG)

**NEW in v2.9.6 (regression fix + testpaths gap closed):**
- Fixed 2 tests in `tests/test_rust_debug_phases_2_3.py` broken by v2.9.5's new borrow-checker `category` filter (hand-built error fixtures predating that field silently got zero patterns back). Added a regression test locking in the filter's actual contract.
- `pytest.ini`'s `testpaths` never included the top-level `tests/` directory, so every past "N/N passing" count in this file, CHANGELOG.md, and MANIFEST.txt never actually ran those 2 (now 3) tests — this is how the regression went undetected by v2.9.5's own dogfooding run. Fixed `testpaths` to cover both directories; single `pytest` run now reports 482 passed, 60 skipped, 0 failed.
- See CHANGELOG.md [2.9.6] for full detail.

**NEW in v2.9.5 (STUBS.md inventory: all STUB items fixed):**
- `RustDebugger` Phase 0: real static analysis (delimiter balance + `todo!()`/`unimplemented!()`/`unreachable!()` detection) replacing the hardcoded `phase_0_ok = True` placeholder, now wired into `debug()`'s actual risk classification.
- `test_generator`: every metamorphic-relation test type (not just symmetry) used to emit empty `inputs={}`, silently producing a no-op `pass` test; now generates real, type-sampled inputs and a real assertion per relation, verified end-to-end against both correct and broken implementations. `run_tests()`/`measure_coverage()` now really invoke pytest/coverage.py or Jest, replacing hardcoded-zero stubs. `run_fuzzing()`'s hardcoded `coverage_estimate: 0.75` replaced with a real measurement (or honest `None`).
- `javascript_debug`: `JavaScriptDebugger.execute_with_debug()`/`analyze_patterns()` were a bare `pass`; now really invoke Node.js. Found and fixed two real, 100%-reproducible bugs in `debug-engine.js` this uncovered: an unclosed `logVariable()` call (syntax error on every declaration) and a missing `return value` (every instrumented variable silently became `undefined`).
- `troubleshooting/diagnostics.py`'s three previously-dead, always-fake-result classes (`UniversalTroubleshooter`, `ToolDiagnostician`, `HealthChecker`) are now real and exported from `__init__.py`.
- Version-string drift across `src/__init__.py`/`INTEROP.yaml`/`MANIFEST.txt`/`SKILL.md` reconciled to 2.9.5.
- 44 new tests. See CHANGELOG.md [2.9.5] for full detail.

**Earlier releases (v1.0 through v2.9.1):** full per-release detail for all of these lives in CHANGELOG.md, which is packaged alongside this file — read it before assuming a component is a stub or that a past finding wasn't fixed. Highlights: v2.9.1 fixed two hardcoded-stub regressions found by body-diffing (`MasterDebugger.classify_risk()`, `RustDebugger.phase_2_formal()`); v2.9.0 added `EquivalenceVerifier` (real code-to-code equivalence checking); v2.8.0 replaced `ContractVerifier`'s non-functional stub with a real Z3 implementation; v2.7.0 was a six-archive branch reconciliation; v2.6.0-2.6.1 added valgrind/cppcheck/semgrep/lief integrations and fixed several silent-failure bugs (bandit never matching, CBMC 6.x flag incompatibility); v2.5.0 added Assembly Phases 8-10; v2.4.0 added DWARF/CBMC-KLEE/C-Debug Phases 5-7; v2.3.0 added LoopVerifier/ContractSimplifier and fixed several self-analysis bugs; v2.2.0 added C/C++-Debug; v2.1.0 added Rust-Debug.

**NEW in v2.1:** Rust-Debug (Phases 2-3).

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
| **cpp-debug** | v1.2 | Compiler diagnostics + Clang Static Analyzer + DWARF analysis (Phase 5) + CBMC/KLEE symbolic execution (Phase 6) | ✅ Complete |
| **c-debug** | v1.0 | C-specific debugger: CppDebugger + strace syscall tracing (Phase 7) | ✅ Complete |
| **assembly-debug** | v1.0 | Capstone disassembly + CFG (Phase 8) + taint analysis (Phase 9) + angr symbolic execution (Phase 10) | ✅ Complete |
| **master-debugger-v5** | v5.0 | 4-phase orchestrator (static → runtime → formal → design) with cross-language support | ✅ Complete |
| **pyprover** | v14.3 | Formal verification with Z3 (Phase 2: contracts, quantifiers, ghost state, len/abs/min/max/string predicates; Phase 3: tokens/async/FFI) | ✅ Complete |
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

### Master Debugger

```python
from debug_suite import MasterDebugger
import asyncio

debugger = MasterDebugger()

# Full 4-phase async debug run
report = asyncio.run(debugger.debug_comprehensive(code, language="python"))

# UnifiedDebugReport fields (actual):
print(report.risk_level)        # RiskLevel.CRITICAL / HIGH / MEDIUM / LOW
print(report.overall_health)    # "✅ VERIFIED" or "⚠️  N issue(s) found"
print(report.confidence_score)  # 0.0–1.0 float
print(report.pyprover_result)   # dict from PyProver, or None
print(report.test_suite)        # auto-generated pytest code (str), or ""
print(report.token_cost)        # estimated token usage (int)

# Classify risk only
risk_info = asyncio.run(debugger.classify_risk(code))
# Returns dict with risk_level, factors, recommendation

# Phase-level access via the phases module:
from debug_suite.master_debugger.phases import (
    Phase0StaticAnalysis,   # mypy + pylint + bandit
    Phase1RuntimeDebug,     # python-debug execution tracing
    Phase2FormalVerification, # PyProver contract verification
    Phase3DesignReview,     # troubleshooter 5-phase diagnosis
)
p0 = Phase0StaticAnalysis.run(code)   # → StaticAnalysisResult
p1 = Phase1RuntimeDebug.run(code)     # → RuntimeDebugResult
p2 = Phase2FormalVerification.run(code) # → FormalVerificationResult
p3 = Phase3DesignReview.run(code)     # → DesignReviewResult
```

> **Note on class name:** as of v2.7.0, `master_debugger` exports **both** `MasterDebugger` (v6, active — supports all languages, async `debug_comprehensive()`) and `MasterDebuggerV5` (legacy, sync `debug()`, Python/JS only, kept for backward compatibility). Versions 2.2.x–2.6.1 only exported `MasterDebuggerV5`; `MasterDebugger` existed in `orchestrator.py` but was dead code, unimported anywhere — this was fixed in v2.7.0's branch reconciliation. Prefer `MasterDebugger` for new code.

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

### PyProver v14.3

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

# Quantified postconditions (new in v14.2) -- forall/exists over a real Z3
# quantifier, wired transparently through the same # Post:/# Pre: scanning:
code = """
def f(n):
    # Pre: n > 0
    # Post: all(i >= 0 for i in range(0, n))
    return list(range(n))
"""
result = verify_contract(code)  # result['verified'] is True, real Z3 check

# Ghost state (new in v14.2) -- spec-only auxiliary variables, checked with
# real Z3 for consistency rather than just recorded:
from debug_suite.pyprover import GhostStateTracker
decls, updates = GhostStateTracker.extract(source_code)  # scans # Ghost:/# GhostUpdate:
ghost_result = GhostStateTracker.check_consistency(decls, updates, real_var_env, expr_to_z3)
print(ghost_result.consistent, ghost_result.detail)

# len()/abs()/min()/max() and string predicates (new in v14.2->v14.3) -- these
# used to silently degrade to "non-arithmetic, skipped" with no warning:
code = """
def f(arr):
    # Pre: len(arr) > 0
    # Post: len(result) == len(arr)
    return arr
"""
result = verify_contract(code)  # now a real, checked verification

code = """
def f(s):
    # Pre: s == "hello world"
    # Post: str_contains(s, "world")
    return s
"""
result = verify_contract(code)  # backed by real Z3 String theory
```

**Not yet integrated:** quantified loop invariants (`# Inv: all(...)`) currently degrade to an honest `skipped` result rather than being proven inductively -- see `roadmap.md` §18.2 for why (PRESERVATION needs induction, not the single-state check quantifiers.py provides) and what the real fix would take. Float precision (`FloatWorkAround`-equivalent, e.g. approximate float comparison) is also not yet integrated -- see roadmap.md §19.3.

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
| **master-debugger** | `src/master_debugger/tests/test_orchestration.py` + `test_synthesis_conflict_resolution.py` | 29 | ✅ |
| **python-debug** | `src/python_debug/tests/test_execution_tracing.py` + `test_unhandled_exception_pattern.py` | 39 | ✅ |
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

**Tooling dependencies (external):**
- **Static analysis (Phase 0, Python):** requires mypy, pylint, bandit installed
- **Z3 solver (Phase 2, loop verification, contract simplification):** requires z3-solver package; all Z3-dependent components degrade gracefully when not installed
- **Rust-Debug:** requires rustc + cargo clippy; degrades to empty findings otherwise
- **Cpp-Debug:** requires clang/clang++; degrades to empty findings otherwise; diagnostic-based, not a full AST transformer
- **GitHub analysis (code-orchestrator):** requires read access to repositories

**PyProver — what's in the bundled src/pyprover vs. the full lineage:**
The bundled PyProver is a curated subset, not a full port of the v6–v14 lineage. Confirmed present: `ContractVerifier` (comment-annotation scanning; real Z3 checking as of v2.8.0 — precondition satisfiability, postcondition *validity* via implication-checking for non-`result`-referencing clauses, satisfiability-only for `result`-referencing clauses since the return expression itself isn't evaluated, invariant satisfiability), `AsyncVerifier` (regex-based concurrency heuristics), `FFIVerifier` (FFI type/memory/lifetime safety, reachable via `PyProverBridge.verify_ffi()`), `LoopVerifier` (Z3 INIT + PRESERVATION for arithmetic invariants, new in v2.3), `ContractSimplifier` (Z3 implication-check redundancy elimination, new in v2.3). Confirmed absent: parallel/batch verification (ThreadPoolExecutor), SymPy-accelerated expression simplification, Hypothesis property-based test generation, beartype runtime type checking, CBMC/KLEE bounded-model-checking, and real per-language AST adapters (the `ContractVerifier` comment scanner is language-agnostic text parsing regardless of declared language — real per-language adapter source now recovered in `legacy_code/pyprover_v11_adapters/`, not yet integrated, see roadmap.md §12.6/§13.4). The `hypothesis` package was in `requirements.txt` but never imported anywhere in the suite — this phantom dependency was removed in v2.7.0 (kept only as a commented-out future-dependency note for the not-yet-built `HypothesisIntegrator`).

**LoopVerifier scope (v2.3):** verifies INIT (invariant is satisfiable at loop entry) and PRESERVATION (inductive for integer iteration variables named i/j/k/idx/n/count). Does not perform full symbolic execution of arbitrary loop bodies. Invariants must be arithmetic expressions over integer variables; string/list/object invariants are skipped with a clear note. TERMINATION is not verified (requires an explicit bound expression beyond what the current annotation syntax supports).

**ContractSimplifier — what it actually does (read this before using it or explaining it):** `ContractSimplifier.simplify(requires: List[str], ensures: List[str])` takes a **contract specification** — the clause strings already extracted from `# Pre:`/`# Post:` annotations by `ContractVerifier.parse_contract()` — and removes clauses that are **logically redundant given the other clauses in the same spec**: a `requires` clause implied by the conjunction of the other `requires` clauses (e.g. `"n >= 0"` is redundant when `"n >= 0 and n < 10"` is also a precondition), an `ensures` clause implied by the preconditions plus the other `ensures` clauses, or a tautology (`"True"`, `"n == n"`). The proof mechanism (Z3 implication-checking: negate the candidate clause, assert it alongside the others, check UNSAT) is real and sound — clauses Z3 can't decide within the timeout are always kept, never silently dropped.

**What it does NOT do, because this is the natural but wrong reading of "simplifier":** it does not take a function's code and prove that a *simplified or rewritten version of that code* would produce the same result. It never sees the function body at all — its only input is a list of clause strings. **If you want that** — code-to-code equivalence checking, or deriving a simplified equivalent of a function's actual computation — **use `EquivalenceVerifier` (`src/pyprover/equivalence_verifier.py`, new in v2.9) instead**, described just above in the components list. `ContractSimplifier` and `EquivalenceVerifier` are deliberately separate tools operating on deliberately different inputs (a contract spec vs. a function body); naming them both "simplifier"-adjacent is exactly the ambiguity this note exists to head off.

**ContractSimplifier scope (v2.3):** integer arithmetic clauses only; string/boolean/list expressions may be kept unconditionally if Z3 can't parse them (conservative, soundness-preserving).

**EquivalenceVerifier scope (v2.9):** straight-line and branching integer/boolean arithmetic only (reuses `contract_verifier.py`'s expression translator, so the same operator set: `+ - * // / % < <= > >= == != and or not`). Function calls (including recursion), list/dict/string operations, generators, and mutation of aliased objects are rejected as `UnsupportedConstructError`, never guessed at. Loops are supported only as `for x in range(N)` with a *literal* `N`, unrolled up to `max_unroll` (default 64) — this proves equivalence up to that bound, not for arbitrary `N`, the same bounded-verification caveat CBMC/KLEE already carry elsewhere in this suite. A bare boolean-typed variable used directly with `and`/`or`/`not` (e.g. `not flag`) hits a real, inherited limitation: the reused expression translator always seeds an unbound name as a Z3 `Int`, so `Not()` on it is a sort mismatch — reported as `status="unsupported"` with an explanatory reason, not a crash; use an Int-typed comparison instead (e.g. `flag > 0`). `propose_redundant_branch_removal()` is the only pattern-matched rewrite proposer shipped — deliberately one narrow, hand-verified pattern, not a general search; every candidate it proposes is run back through `verify_function_equivalence()` before being returned, so nothing unverified is ever surfaced as a suggestion.

**FFIVerifier wiring (v2.3):** `PyProverBridge.verify_ffi()` synthesizes a minimal FFIContract from the first function signature found via regex. It is a heuristic entry point. For precise FFI checking, construct `FFIContract`/`FFISignature` explicitly and call `FFIVerifier.verify()` directly.

**AsyncVerifier:** text/regex-based heuristic, not AST-based. Can misfire on files whose source is *about* concurrency detection (e.g. analyzing `async_verifier.py` itself). Does not handle multi-line triple-quoted docstrings.

**MasterDebugger class name:** the active orchestrator is `MasterDebugger` (not `MasterDebuggerV5`, which was a documentation error in versions ≤ 2.2.x). As of v2.7.0, both are properly exported from `master_debugger/__init__.py` — `MasterDebuggerV5` is preserved in `orchestrator_v5.py` for backward compatibility, but was the only one importable prior to v2.7.0 (`MasterDebugger` was dead code, unimported anywhere, from v2.2.x through v2.6.1).

**`get_variable_mutations()` return type:** returns `List[Tuple[lineno, prev_value, new_value]]` (plain tuples), not named objects. The SKILL.md Quick Start examples above use the correct tuple format.

**Phase 5 (DWARF):** Requires pyelftools (`pip install pyelftools`) and a C/C++ compiler with `-g`. Heuristics (stack-pointer escape, void\* allocation, multi-pointer double-free) are intentionally conservative (confidence 0.4-0.55); they produce false positives. Use them as signals, not verdicts.

**Phase 6 (CBMC/KLEE):** CBMC must be installed separately (`apt install cbmc`). KLEE requires a full LLVM build; use the Docker image (`docker pull klee/klee`). CBMC's `--unwind 5` bound may miss issues in loops that require more than 5 iterations to expose. KLEE is skipped for C++ dialects.

**Phase 7 (strace/C-Debug):** strace is Linux-only. On macOS, use `dtruss` (requires `sudo`) or `dtrace`. The SyscallTracer compiles and executes the code — only safe to use on trusted inputs in an isolated environment. Timeout is 5 seconds by default.

**Assembly debug (Phases 8-10):** Phase 8 (Capstone) requires `pip install capstone`. Phase 10 (angr) requires `pip install angr` (~400 MB); use a virtualenv. Taint analysis (Phase 9) is intra-procedural and x86-64-only for now; ARM register canonicalisation is not fully implemented. The angr simulation manager uses `LAZY_SOLVES` mode and runs for 30 steps by default — complex programs may need more steps to find bugs. angr's unicorn engine is disabled in most sandbox environments (unicornlib.so not found); this limits concrete execution speed but not correctness.

---

## Roadmap

See `roadmap.md` (packaged alongside this file) for the full feature-restoration backlog: three divergent historical PyProver development branches that were never reconciled, a prior completeness audit shown to be unreliable against the actual code, and the original C/C++/Assembly Phases 4-10 plan with current status and 25+ linked source chats. A `legacy_code/` folder (also packaged alongside this file) contains real, recovered-but-untested code fragments for several of the highest-value missing features (loop invariant verification, contract simplification, the JS Node.js parser speedup, the multiline-contract regex fix, the language-adapter interface) so a future agent doesn't have to re-search conversation history from zero - see `legacy_code/README.md`.

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

Full per-release detail for every entry below (and the "NEW in vX.Y" bullets above) lives in CHANGELOG.md, packaged alongside this file — read it before assuming a component is a stub or that a past finding wasn't fixed.

- **v2.9.6** (2026-07-11): Fixed 2 tests broken by v2.9.5's borrow-checker `category` filter; closed a `pytest.ini` `testpaths` gap that had excluded the top-level `tests/` directory from every past suite-wide pass/fail count
- **v2.9.5** (2026-07-11): STUBS.md inventory — all documented STUB items fixed (rust_debug Phase 0, test_generator metamorphic/coverage/fuzzing stubs, troubleshooting/diagnostics.py's three dead classes, javascript_debug's execute_with_debug/analyze_patterns)
- **v2.9.4** (2026-07-10): Two severe synthesis bugs fixed in the bug-detection tool's own aggregation logic (unhandled-exception dispatch gap; `report.issues_found` never receiving static/runtime findings) — added explicit `⚠️ CONFLICT` state
- **v2.9.3** (2026-07-10): Real `len()`/`abs()`/`min()`/`max()` and string-predicate support across all three AST-to-Z3 translators — the highest-impact silent gap found in the verifier so far
- **v2.9.2** (2026-07-10): Real `forall`/`exists` quantifier support and Z3-backed ghost state tracking
- **v2.9.1** (2026-07-10): Two real stubs found and fixed via body-diffing (not just name-presence comparison) against the sibling v2.5.2 archive
- **v2.9.0** (2026-07-10): New `EquivalenceVerifier` — real code-to-code equivalence checking and Z3-backed simplification
- **v2.8.0** (2026-07-10): Replaced `ContractVerifier`'s non-functional stub with a real Z3-based implementation from the sibling archive
- **v2.7.0** (2026-07-10): Six-archive branch reconciliation with sibling v2.5.2, plus same-day bugfixes (RiskLevel unification, `contract_simplifier.py` Z3 crash, `MasterDebuggerV5` input()-hang)
- **v2.6.0-2.6.1** (2026-07-09): valgrind/cppcheck/semgrep/lief integrations; fixed bandit never matching real output and a CBMC 6.x flag-incompatibility silent-failure
- **v2.5.0** (2026-07-09): Assembly Phases 8-10 (Capstone disassembly/CFG, taint dataflow, angr symbolic execution)
- **v2.4.0** (2026-07-04): DWARF (Phase 5), CBMC/KLEE (Phase 6), C-Debug + strace (Phase 7)
- **v2.3.0** (2026-07-04): LoopVerifier, ContractSimplifier, and a self-analysis bugfix pass across the suite
- **v2.2.0** (2026-06-30): C/C++-Debug (Phase 4) + suite-wide bugfix pass
- **v2.1.0** (2026-06-28): Rust-Debug (Phases 2-3)
- **v1.2.0** (2026-06-28): JavaScript-Debug merged in; cross-language support
- **v1.0.0-v1.0.1** (2026-06-24): Production release, all 4 phases complete
- **v0.5.0-v0.9.0** (2026-06-22/23): Beta/Alpha releases

For full detail on any entry above, see CHANGELOG.md.

