# debug-suite: Stub Inventory

**Status as of v2.9.5 (2026-07-11): every item in the STUB section below has
been fixed — see CHANGELOG.md [2.9.5] for what changed and why, and each
component's new test file for regression coverage.** The inventory itself is
left intact below as a historical record of what was found and how, per this
suite's own convention of not silently editing away a documented finding.
The DEAD section's `troubleshooting/diagnostics.py` classes are likewise
resolved (implemented, not deleted — see CHANGELOG.md [2.9.5]); its
`common/interop.py` item was already fixed before this inventory was written.
PARTIAL and SCOPED remain accurate, documented, non-bug limitations.

Compiled 2026-07-11 via systematic grep (`TODO`/`FIXME`/`placeholder`/`stub`/
`NotImplementedError`) across `src/`, then hand-verified each hit to sort
real gaps from defensive exhaustiveness guards and documentation mentions of
historical (already-replaced) placeholders. Status tags:

- **STUB** — always returns the same canned result regardless of input, or
  does nothing at all. Looks like a real implementation from the outside.
- **PARTIAL** — does something real but a documented piece is missing.
- **SCOPED** — an intentional, honestly-commented limitation, not a gap.
- **DEAD** — a stub, but unreachable: nothing in the suite calls it.

---

## STUB

### `rust_debug/phases.py` — Phase 0 static analysis
`phase_0_static()` and the inline `phase_0_ok = True  # Placeholder` in
`debug()` always return/assign `True` regardless of the code passed in. No
AST inspection or pattern check actually runs, despite the docstring calling
this "Phase 0: Static analysis." The rationalizing comment ("Rust's type
system is already the static analyzer") doesn't hold up on its own terms —
the type system only runs *after* successful compilation via Phase 1; there
is no equivalent to the AST-level pre-compile pattern checks that Python's
Phase 0 and C/C++'s Clang diagnostics provide. `phase_0_ok`'s value is never
even read downstream in `debug()` — it's a dead variable on top of being a
stub.

### `troubleshooting/diagnostics.py` — entire module (see DEAD below)
`UniversalTroubleshooter._suggest_fixes()` ignores the `state` argument it's
given and always returns the identical `{"cause": "Unknown error", ...,
"confidence": 0.7}` regardless of what was diagnosed.
`ToolDiagnostician.diagnose_pyprover_failure()` always returns
`{"suggestions": ["Simplify code"]}` regardless of the actual exception.
`HealthChecker.check_all_tools()` is hardcoded to report every tool as
`"healthy"` unconditionally — structurally incapable of ever reporting a
real problem.

### `javascript_debug/__init__.py` — `JavaScriptDebugger`
`execute_with_debug()` and `analyze_patterns()` are both a bare `pass`. The
docstring says "the heavy lifting is in JavaScript" — and that part is true,
`debug-engine.js` (463 lines) and `bug-patterns.js` are real, substantial
implementations — but this Python orchestration class, the one thing a
Python caller would actually instantiate, does nothing. See also the
`common/interop.py` fix below: even the routing to find this class was
broken until this session.

### `test_generator/test_generator.py` — several
- `run_tests()`: always returns `{"passed": 0, "failed": 0, "message":
  "Test execution requires pytest/jest installed"}` — never actually runs
  anything, even when pytest/jest genuinely are installed.
- `measure_coverage()`: always returns `{"line_coverage": 0.0,
  "branch_coverage": 0.0}` — never calls `coverage.py`, hardcoded zero
  regardless of the code/tests passed in.
- `run_fuzzing()`'s `"coverage_estimate": 0.75` — a hardcoded constant
  presented as a measured value, not derived from anything about the
  specific code being analyzed.
- Symmetry/metamorphic test generation (`test_{func}_symmetry`) emits
  `inputs={}` — an empty input set, so the generated test has no actual
  arguments to run with.
- The general test-body generator, when no specific test-type template
  matches, emits literal `# TODO: Implement test` / `pass` (Python) or
  `// TODO: Implement` (JS) directly into **generated output** — i.e. a
  user could receive a "generated test" that is just an empty stub, not
  only an internal placeholder.

---

## DEAD (stubs that are also unreachable)

`troubleshooting/diagnostics.py`'s three classes
(`UniversalTroubleshooter`, `ToolDiagnostician`, `HealthChecker`) are never
imported anywhere else in `src/`, and `troubleshooting/__init__.py` only
exports `Troubleshooter`/`DiagnosisResult` from the separate, more complete
`phases_5.py` module (the one enriched this session — see CHANGELOG). So
this file's stubs are currently inert rather than live-and-wrong, but the
file is still shipped and importable directly
(`from src.troubleshooting.diagnostics import HealthChecker`), so anyone
who imports it directly rather than going through `__init__.py` would get
fake results with no signal that they're fake.

`common/interop.py`'s `LanguageDetector.get_debugger_for_language()` was
also dead (nothing in the suite calls it) *and* broken (both branches
imported from a nonexistent `verification_debugging_suite` package). Fixed
this session (relative imports) since it's part of the public `common`
API surface and one line to fix per branch, even though nothing currently
depends on it working.

---

## PARTIAL

### `pyprover/*` — float/Real-sort precision (documented in roadmap.md §19.3)
Z3's native `Real`/`FP` sorts were never wired in; the old
`FloatWorkAround` int-scaling approach from PyProver v6.1/v7.0 was
deliberately not ported (would be worse than the Z3-native alternative),
but the Z3-native alternative itself isn't built yet either. Contracts
involving float comparisons silently skip verification rather than
erroring, same "quietly unverified" pattern as the `len()`/`abs()` gap
that v2.9.3 fixed for other builtins.

### `pyprover/contract_verifier.py` — vacuous-true verification
`verify_contract()` returns `verified: True` for code with zero `# Pre:`/
`# Post:` annotations — "nothing was checked" is indistinguishable from
"checked and correct" in the result. Documented in roadmap.md §20.3 as a
known, judged-acceptable nuance rather than a bug, but worth listing here
since it does mean a "verified" result doesn't always mean what it sounds
like it means.

---

## SCOPED (intentional, not gaps)

- `pyprover/{contract_verifier,loop_verifier,contract_simplifier}.py` raise
  `NotImplementedError` for AST node types outside each module's documented
  supported-syntax subset (unsupported `BinOp`/`UnaryOp`/`Compare`/`Call`
  variants). This is a defensive exhaustiveness guard with a bounded,
  documented feature surface — callers catch it and degrade gracefully
  (confirmed in `equivalence_verifier.py` and `loop_verifier.py`'s own
  `except NotImplementedError` blocks) rather than crashing silently.
- `assembly_debug/dataflow.py`: `pass  # simplified: don't model stack
  memory` — an honestly-commented analysis-scope limitation.
- `assembly_debug/cfg.py`: `pass  # target not statically known` — same,
  for indirect jump targets that genuinely can't be resolved statically.

---

## Not a stub (false positives from the initial grep, listed for completeness)

- `pyprover/quantifiers.py`'s "placeholder" mention is in a docstring
  describing the *historical* placeholders this module replaces with a
  real quantifier implementation — the module itself is real, not a stub.
- `c_debug/debugger.py`'s "stub." match is the tail end of a comment
  explicitly stating valgrind integration is "a real detector, not a
  stub" — the opposite of a finding.
- `code_orchestrator/type_stubs.py` — "stub" here means Python type-stub
  in the `.pyi`/type-hint sense (shared dataclasses/type aliases), not an
  incomplete implementation.
