---
name: debug-suite
description: >
  Unified debugging and verification suite for 12+ languages. Full support for Python, JavaScript, Rust
  (Phases 2-3: borrow checker + clippy, with honest tool-availability reporting), C/C++ (Phase 4: compiler
  diagnostics + Clang Static Analyzer + cppcheck second opinion), DWARF binary analysis (Phase 5: memory
  layout + use-after-free heuristics via pyelftools), CBMC/KLEE symbolic execution (Phase 6: exhaustive path
  checking), C-specific syscall tracing via strace + valgrind memcheck dynamic memory-error detection
  (Phase 7: double-close, fd leaks, unchecked malloc, leaks, invalid read/write, use-after-free), and full
  Assembly support (Phases 8-10: Capstone disassembly + CFG construction, register dataflow taint analysis,
  angr symbolic execution for crash detection).
  Combines runtime debugging, static/formal analysis (PyProver with loop invariant verification + contract
  simplification), test generation (with expected-output inference and code-pattern red team), and problem
  diagnosis. Features 4-phase automated debugging with risk classification, FFI boundary safety checking,
  graceful tool degradation, and automatic regression test generation when issues are found.
  MasterDebugger orchestrates all phases.

compatibility: "Python 3.8+; z3-solver for formal verification; Rust toolchain (rustc+clippy, or apt package rust-clippy) recommended for Rust; Clang and cppcheck recommended for C/C++; valgrind recommended for C dynamic memory-error detection; CBMC 6.x for symbolic execution (flag names changed from 5.x - see CHANGELOG 2.6.0); bandit and semgrep recommended for Python security analysis (semgrep uses a locally-bundled ruleset, not the semgrep.dev registry); lief recommended for C/C++ binary hardening analysis"

metadata:
  version: 2.6.1
  status: production
  interop_level: 4
---

# Debug Suite v2.6.1

**Status:** Production Ready | **Components:** 18 | **Test suite:** 359/359

**NEW in v2.6.1 (this release, same-day follow-up to v2.6.0):**
- **`RiskLevel` enum unification**: the three separate `RiskLevel` classes documented as unresolved in v2.6.0 are now one. `src.RiskLevel is common.interop.RiskLevel` (literally the same class), so `report.risk_level == src.RiskLevel.X` now works correctly for reports from every component, not just `MasterDebuggerV5`.
- **bandit fix**: `Phase0StaticAnalysis`'s bandit integration never actually surfaced a finding on any input - its match condition (`'WARNING' in output.stdout`) never matched real bandit output. Fixed via `-f json` parsing; verified against real vulnerable code.
- **semgrep integration** (`src/common/semgrep_analyzer.py`): pattern-based second opinion alongside bandit, using a locally-bundled 20-rule security ruleset (semgrep.dev's registry isn't reachable from sandboxed environments - see `semgrep_rules/README.md`). Adds a disclosed ~6-8s per-call latency cost.
- **lief integration** (`src/cpp_debug/lief_analyzer.py`): compiled-binary hardening posture (PIE/NX/RELRO/stack-canary) and dangerous-import detection (`system`, `strcpy`, `gets`, ...), a capability none of the source-level C/C++ analyzers have. Found and fixed a self-inflicted risk-classifier regression during verification (hardening findings are toolchain-constant, not code-content-dependent - excluded from automatic risk scoring, available via a direct call).
- **Known issues found, not fixed**: `MasterDebuggerV5.debug()` can hang indefinitely on traced code that calls `input()` (no stdin in sandboxed environments); `master_debugger/orchestrator.py`'s `MasterDebugger` class ("v6" per its docstring) is dead code, more capable than the exported `MasterDebuggerV5` but never wired in. Both documented in `roadmap.md` §11.9/§11.7 for a future session.
- See `CHANGELOG.md` [2.6.1] and `roadmap.md` §11.6-§11.15 for full details.

**NEW in v2.6.0:**
- **Root `src/__init__.py` rebuilt from scratch** — the v2.5.0 archive shipped it completely empty (0 bytes), meaning `import src; src.MasterDebuggerV5(...)`-style single-import usage never actually worked despite every underlying component being real and functional. Now 59 verified exports (`hasattr`-checked, not just import-success-checked).
- **Valgrind memcheck integration** (`src/c_debug/debugger.py`): `ValgrindRunner`/`ValgrindReport`/`valgrind_available()`, wired into `CDebugger.debug()`. Dynamic memory-error detection (leaks, invalid read/write, invalid/double free, uninitialised-value use) — the first dynamic *memory* analysis in the suite, complementing strace's dynamic *syscall* analysis.
- **Cppcheck second-opinion static analyzer** (`src/cpp_debug/cppcheck_analyzer.py`): `CppcheckAnalyzer`/`cppcheck_available()`, wired into `CppDebugger.debug()`. Dataflow-based analysis alongside Clang/CSA's AST-diagnostic approach.
- **RustDebugger honesty fix**: previously reported `confidence=0.95, "no violations"` even when rustc/clippy weren't installed at all. Now reports `confidence=0.0` and an explicit warning in that case.
- **CBMC 6.x compatibility fix**: `--null-pointer-check`/`--overflow-check` (CBMC 5.x) renamed/split in CBMC 6.x, silently disabling all CBMC checking on 6.x installs (hard usage error → zero findings, indistinguishable from "checked, clean"). Fixed.
- **rust_debug/setup.py**: now leads with apt-based install (verified working in sandboxed environments) rather than the rustup.rs curl-installer, which requires network access many sandboxes don't allow.
- **Test count:** 355 → 359 passing (4 previously-`skipif`-skipped CBMC/cppcheck integration tests now actually exercised against real installed tools for the first time).

**NEW in v2.5:**
- **Phase 8: Assembly Disassembly & CFG** (`src/assembly_debug/disassembler.py`, `cfg.py`): Capstone-based disassembler supporting x86-64, x86-32, ARM, ARM64. Reads raw bytes or ELF `.text` sections. CFGBuilder partitions instructions into basic blocks, computes control-flow edges, detects back edges (loops via DFS), unreachable blocks, indirect jumps, and functions with no return path. 26 new tests.
- **Phase 9: Dataflow & Taint Analysis** (`src/assembly_debug/dataflow.py`): worklist-based forward taint analysis over the CFG. Seeds function argument registers (rdi/rsi/rdx/rcx/r8/r9) as tainted; propagates through mov/add/sub/xor; reports tainted-to-memory-write, tainted-to-indirect-branch (ROP vector), and tainted-to-syscall-arg sinks. 33 new tests.
- **Phase 10: angr Symbolic Execution** (`src/assembly_debug/symbolic.py`): loads ELF binaries into angr, runs CFGFast for function/block extraction, and drives the simulation manager to find unconstrained instruction-pointer states (buffer overflows / exploitation primitives) and concrete crashes. 27 new tests.
- **AssemblyDebugger** (`src/assembly_debug/phases.py`): unified facade combining Phases 8-10. `debug_bytes(data, arch)`, `debug_binary(path)`, `debug_source(code, dialect)` — all return `UnifiedDebugReport`. MasterDebugger routes `language="assembly"/"asm"/"x86_64"/"arm"` to AssemblyDebugger automatically.
- **Test count:** 265 → 355 (90 new tests across Phases 8, 9, 10).

**NEW in v2.4:**
- **Phase 5: DWARF Symbol Analysis** (`src/cpp_debug/dwarf_analyzer.py`): reads DWARF debug info from ELF binaries compiled with `-g` via pyelftools. Extracts variable/type layout (name, type, byte size, stack/global classification), detects stack-pointer escapes, void* heap allocations, and multi-pointer double-free candidates. Integrated into `CppDebugger.debug()`. 28 new tests.
- **Phase 6: CBMC/KLEE Symbolic Execution** (`src/cpp_debug/symbolic_executor.py`): drives CBMC (primary; `apt install cbmc`) and KLEE (secondary; Docker) for exhaustive path analysis. Detects buffer overflows, null dereferences, division by zero, assertion violations, and memory leaks that compiler warnings and the Clang Static Analyzer miss. Integrated into `CppDebugger.debug()`. 35 new tests (2 skipped — no CBMC in CI).
- **Phase 7: C-Debug** (`src/c_debug/`): dedicated C-specific debugger combining CppDebugger analysis (Phases 4-6) with strace syscall tracing. Detects double-close, write-after-close, unchecked malloc failure, unchecked open failure, and fork/exec fd-leak risk from actual program execution. `MasterDebugger` now routes `language="c"` to `CDebugger` first, falling back to `CppDebugger` if needed. 29 new tests.
- **Test count:** 173 → 265 (92 new tests across Phases 5, 6, 7).

**NEW in v2.3:**
- **Bug fixes (all from self-analysis):** `ContractVerifier.parse_contract()` now correctly finds `# Pre:`/`# Post:`/`# Inv:` annotations (was a no-op on all real input); `Phase1RuntimeDebug` import errors fixed (Phase 1 now actually runs inside the orchestrator); `DiagnosisResult` field access fixed in Phase 3 design review; test generator emits the correct function name in generated test code; 9 dead f-strings and 2 unencoded `open()` calls cleaned up in `python_debug/debug_report.py`.
- **LoopVerifier** (`src/pyprover/loop_verifier.py`): Z3 INIT + PRESERVATION proof obligations for while-loop invariants annotated as `# Invariant: expr`. Supports arithmetic expressions, multiple loop variables, graceful degradation if z3-solver not installed.
- **ContractSimplifier** (`src/pyprover/contract_simplifier.py`): Iterative Z3 implication checking removes redundant `@requires`/`@ensures` clauses. Soundness-preserving: timed-out clauses are always kept.
- **FFI verifier wired** into `PyProverBridge.verify_ffi()` and `verify_loop_invariants()` — both now reachable via the bridge without direct import.
- **Test generator → MasterDebugger wiring**: `debug_comprehensive()` now automatically generates a regression test suite via `test_generator` when issues are found (per roadmap memory instruction).
- **Expected output inference**: test generator now executes deterministic functions with generated inputs and captures real expected values (replacing `# TODO: Verify expected output` stubs).
- **Code-pattern red team**: red team tests now fire based on what the code does (`eval()`/`exec()` injection tests, `open()` path traversal tests) rather than only on docstring keywords.

**NEW in v2.2:** C/C++-Debug (Phase 4), suite-wide bugfix pass (144/144 tests passing).

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

> **Note on class name:** the orchestrator class is `MasterDebugger` (not `MasterDebuggerV5` as documented in versions ≤ 2.2.x — that was a SKILL.md documentation error). `MasterDebuggerV5` is the old standalone class in `orchestrator_v5.py` and is kept for backward compatibility but is not the active orchestrator.

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

**Tooling dependencies (external):**
- **Static analysis (Phase 0, Python):** requires mypy, pylint, bandit installed
- **Z3 solver (Phase 2, loop verification, contract simplification):** requires z3-solver package; all Z3-dependent components degrade gracefully when not installed
- **Rust-Debug:** requires rustc + cargo clippy; degrades to empty findings otherwise
- **Cpp-Debug:** requires clang/clang++; degrades to empty findings otherwise; diagnostic-based, not a full AST transformer
- **GitHub analysis (code-orchestrator):** requires read access to repositories

**PyProver — what's in the bundled src/pyprover vs. the full lineage:**
The bundled PyProver is a curated subset, not a full port of the v6–v14 lineage. Confirmed present: `ContractVerifier` (comment-annotation scanning + Z3 satisfiability), `AsyncVerifier` (regex-based concurrency heuristics), `FFIVerifier` (FFI type/memory/lifetime safety, reachable via `PyProverBridge.verify_ffi()`), `LoopVerifier` (Z3 INIT + PRESERVATION for arithmetic invariants, new in v2.3), `ContractSimplifier` (Z3 implication-check redundancy elimination, new in v2.3). Confirmed absent: parallel/batch verification (ThreadPoolExecutor), SymPy-accelerated expression simplification, Hypothesis property-based test generation, beartype runtime type checking, CBMC/KLEE bounded-model-checking, and real per-language AST adapters (the `ContractVerifier` comment scanner is language-agnostic text parsing regardless of declared language). The `hypothesis` package is in `requirements.txt` but never imported anywhere in the suite — a known phantom dependency from an earlier consolidation.

**LoopVerifier scope (v2.3):** verifies INIT (invariant is satisfiable at loop entry) and PRESERVATION (inductive for integer iteration variables named i/j/k/idx/n/count). Does not perform full symbolic execution of arbitrary loop bodies. Invariants must be arithmetic expressions over integer variables; string/list/object invariants are skipped with a clear note. TERMINATION is not verified (requires an explicit bound expression beyond what the current annotation syntax supports).

**ContractSimplifier scope (v2.3):** integer arithmetic clauses only; string/boolean/list expressions may be kept unconditionally if Z3 can't parse them (conservative, soundness-preserving).

**FFIVerifier wiring (v2.3):** `PyProverBridge.verify_ffi()` synthesizes a minimal FFIContract from the first function signature found via regex. It is a heuristic entry point. For precise FFI checking, construct `FFIContract`/`FFISignature` explicitly and call `FFIVerifier.verify()` directly.

**AsyncVerifier:** text/regex-based heuristic, not AST-based. Can misfire on files whose source is *about* concurrency detection (e.g. analyzing `async_verifier.py` itself). Does not handle multi-line triple-quoted docstrings.

**MasterDebugger class name:** the active orchestrator is `MasterDebugger` (not `MasterDebuggerV5`, which was a documentation error in versions ≤ 2.2.x). `MasterDebuggerV5` is preserved in `orchestrator_v5.py` for backward compatibility.

**`get_variable_mutations()` return type:** returns `List[Tuple[lineno, prev_value, new_value]]` (plain tuples), not named objects. The SKILL.md Quick Start examples above use the correct tuple format.

**Phase 5 (DWARF):** Requires pyelftools (`pip install pyelftools`) and a C/C++ compiler with `-g`. Heuristics (stack-pointer escape, void\* allocation, multi-pointer double-free) are intentionally conservative (confidence 0.4-0.55); they produce false positives. Use them as signals, not verdicts.

**Phase 6 (CBMC/KLEE):** CBMC must be installed separately (`apt install cbmc`). KLEE requires a full LLVM build; use the Docker image (`docker pull klee/klee`). CBMC's `--unwind 5` bound may miss issues in loops that require more than 5 iterations to expose. KLEE is skipped for C++ dialects.

**Phase 7 (strace/C-Debug):** strace is Linux-only. On macOS, use `dtruss` (requires `sudo`) or `dtrace`. The SyscallTracer compiles and executes the code — only safe to use on trusted inputs in an isolated environment. Timeout is 5 seconds by default.

**Assembly debug (Phases 8-10):** Phase 8 (Capstone) requires `pip install capstone`. Phase 10 (angr) requires `pip install angr` (~400 MB); use a virtualenv. Taint analysis (Phase 9) is intra-procedural and x86-64-only for now; ARM register canonicalisation is not fully implemented. The angr simulation manager uses `LAZY_SOLVES` mode and runs for 30 steps by default — complex programs may need more steps to find bugs. angr's unicorn engine is disabled in most sandbox environments (unicornlib.so not found); this limits concrete execution speed but not correctness.

- **v2.5.0** (2026-07-09): Assembly Phases 8-10 — 90 new tests, 355 total
  - Phase 8: Capstone disassembler (x86-64/32, ARM, ARM64) + CFGBuilder + CFGAnalysis (back edges, unreachable, indirect, no-return)
  - Phase 9: Register dataflow taint analysis (x86-64 SysV ABI) with worklist fixpoint; detects taint→memory-write, taint→indirect-branch, taint→syscall
  - Phase 10: AngrAnalyzer wrapping CFGFast + SimulationManager; collects unconstrained and errored states
  - AssemblyDebugger facade: debug_bytes / debug_binary / debug_source
  - MasterDebugger: routes language="assembly"/"asm"/"x86_64"/"arm"/"arm64" to AssemblyDebugger

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

- **v2.4.0** (2026-07-04): Phases 5 (DWARF), 6 (CBMC/KLEE), 7 (C-Debug + strace) — 92 new tests, 265 total
  - Phase 5: DWARFAnalyzer via pyelftools (stack-pointer escape, void\* heap, double-free heuristics)
  - Phase 6: SymbolicExecutor wrapping CBMC + KLEE with deduplication and graceful degradation
  - Phase 7: CDebugger (c_debug module) with SyscallTracer — strace fd/syscall analysis for plain C
  - CppDebugger now runs all 6 layers (Phases 4-6) in sequence; plain-C routes through CDebugger
  - MasterDebugger routes `language="c"` to CDebugger; `language="cpp"/"c++"` stays with CppDebugger
- **v2.3.0** (2026-07-04): Bug fixes (self-analysis pass) + PyProver expansion + test-generator improvements
  - Fixed `ContractVerifier.parse_contract()` — was returning garbled results on all real input; now correctly matches `# Pre:`/`# Post:`/`# Inv:` comment annotations
  - Fixed Phase 1 (python-debug) always silently failing inside `MasterDebugger.debug_comprehensive()` — relative import error swallowed; now uses try/except fallback for both package modes
  - Fixed `DiagnosisResult` called as dict in Phase 3 design review (`diagnosis.get(...)` → field access)
  - Fixed test generator emitting wrong function name in generated code (`classify` → actual `func_name` parameter propagated through `format_tests` → `_format_pytest` / `_format_jest`)
  - Added `_infer_expected_outputs()` to test generator: executes deterministic functions with generated inputs and captures real expected values instead of `# TODO: Verify expected output`
  - Added code-pattern red team detection: `eval()`/`exec()` injection tests and `open()` path traversal tests fire based on source analysis, not docstring keywords
  - Fixed 9 f-strings without interpolation in `python_debug/debug_report.py` human-readable output; fixed `open()` without encoding
  - Added **LoopVerifier** (`src/pyprover/loop_verifier.py`): Z3 INIT + PRESERVATION for `# Invariant: expr` annotations in while-loops
  - Added **ContractSimplifier** (`src/pyprover/contract_simplifier.py`): iterative Z3 implication-check clause removal
  - Wired `FFIVerifier` into `PyProverBridge.verify_ffi()` (heuristic entry point from raw source)
  - Added `PyProverBridge.verify_loop_invariants()` convenience method
  - Wired test-generator into `MasterDebugger.debug_comprehensive()` — generates regression tests automatically when issues are found
  - Updated SKILL.md: corrected `MasterDebuggerV5` → `MasterDebugger`; corrected `UnifiedDebugReport` fields; rewrote Known Limitations to reflect actual state
  - Test suite: 111 → 124 passing (13 new tests for LoopVerifier and ContractSimplifier)
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

