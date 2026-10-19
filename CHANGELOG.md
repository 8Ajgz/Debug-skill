# Changelog

## [Unreleased]

### Added

- `src/pyprover/verification_cache.py`: SHA256-keyed, bounded LRU cache for `ContractVerifier` results (roadmap 2.1)
- `src/pyprover/parallel_verifier.py`: `batch_verify()` runs contracts in worker processes; Z3 is not thread-safe on its default context
- `src/pyprover/smtlib_export.py`: `export_smtlib()` emits SMT-LIB v2 scripts from Z3's `to_smt2()`, not a stub
- `src/pyprover/property_tester.py`: `property_test()` checks Python contracts with Hypothesis (optional dependency); clauses are evaluated without `eval()`
- `src/pyprover/invariant_templates.py`: BinarySearchBounds, MinMaxLoop, SumAccumulator, FilterCount, Scan, StateMachine, ported from v8.2; checked against reference loops in tests
- Conditional postconditions: `# Post: if <cond>: <clause>` is checked as Implies(cond, clause) by `ContractVerifier`, `ContractSimplifier` and `property_test`. The `else` form is skipped, not guessed
- Float precision: float literals are exact Z3 reals, variables in float clauses or annotated `float` are Real, and `/` is real division. Before this, float contracts were checked over the integers, which gave wrong verdicts in both directions
- `docs/FEATURE_AUDIT.md`: status of every old feature in the archive, with where it lives and what remains open
- `docs/EVOLUTION.md`: release history and feature-loss audit of the archive

### Fixed

- `rust_debug/borrow_checker.py` linked a binary named after the temp file into the working directory on every check. Now uses `--emit=metadata --out-dir <tempdir>`
- `ContractSimplifier` now uses the verifier's expression translator instead of its own copy
- `python_debug`: `get_variable_mutations()` crashed on timeline events with no snapshot, and dropped mutations for variables first assigned on the last line
- `pytest.ini` sets `pythonpath = src .`, so plain `pytest` collects `common.*` imports

## [2.9.6] - 2026-07-11 (regression fix: v2.9.5's borrow-checker category filter broke 2 existing tests; testpaths gap that hid them also fixed)

### Fixed

**`tests/test_rust_debug_phases_2_3.py` — `test_detect_double_borrow_pattern` and `test_detect_use_after_move_pattern`:** v2.9.5 added a `category` field to `BorrowCheckerParser._parse_diagnostic()`'s output (`"borrow_check"` vs `"dependency_resolution"`, so dependency-resolution noise like unresolved imports/crates isn't misreported as a memory-safety finding) and made `RustBugPatternDetector.detect_patterns()` require `category == "borrow_check"` to consider an error at all. These two tests build error dicts by hand and predate the `category` field, so they silently got zero patterns back instead of the expected one, with no error or warning — the same silent-regression shape this suite's own methodology notes exist to catch. Fixed by adding `"category": "borrow_check"` to both fixtures. Real production behavior was never affected: `rust_debug/phases.py`'s actual call path always builds errors via `_parse_diagnostic()`, which already sets `category` correctly; only hand-built test/caller dicts predating v2.9.5 were exposed.

Added `test_uncategorized_errors_are_filtered_not_detected` to lock in the actual current contract (no `category` key, or any value other than `"borrow_check"`, means "not detected" — not "detected via a default") so this doesn't regress silently again, and so any future caller building error dicts by hand knows `category` is required.

**`pytest.ini`'s `testpaths = src` never included the top-level `tests/` directory** (`tests/test_pyprover_integration.py`, `tests/test_rust_debug_phases_2_3.py`) — meaning every "N/N passing, zero regressions" count in this file and in `SKILL.md`/`MANIFEST.txt`, going back to whenever those two files were added, never actually ran them as part of the suite's own self-check. This is exactly how the regression above went undetected by v2.9.5's own "427 passed, 0 failed" dogfooding claim: that run was real and accurate for what it covered, but it didn't cover these two tests. Fixed `testpaths` to `src tests`. Full suite, single command, this sandbox: 482 passed, 60 skipped, 1 deselected, 0 failed (432 from `src/` + 50 from `tests/`, including the 1 new regression test above).

### Test suite

482 passed, 60 skipped, 1 deselected, 0 failed (single `pytest` run, both `src/` and `tests/` now included).

## [2.9.5] - 2026-07-11 (STUBS.md inventory: all STUB items fixed, plus version-drift reconciliation)

### Fixed

Worked through `STUBS.md`'s full **STUB** inventory in priority order (per `debug-suite-handoff.md`'s Continue-From-Here), then dogfooded the suite by running its own test suite against the changes.

**`rust_debug/phases.py` Phase 0 (`phase_0_static()`):** previously hardcoded `True` unconditionally (`phase_0_ok = True  # Placeholder`), with the assigned value never even read downstream. Replaced with a real `RustStaticAnalyzer` (`rust_debug/static_analyzer.py`) that does genuine pre-compile analysis requiring no toolchain: delimiter-balance checking (catches truncated/malformed source even when rustc isn't installed at all, so Phase 1 never runs) and `todo!()`/`unimplemented!()`/`unreachable!()` incomplete-code-marker detection. Findings now participate in `debug()`'s real risk classification and summary, not just the previously-dead standalone method. 17 new tests (`rust_debug/tests/test_static_analyzer.py`).

**`test_generator/test_generator.py` — several, this was the largest item:**
- `generate_metamorphic_tests()`: every single metamorphic relation (symmetry, idempotence, reflexivity, monotonicity, length-preservation, inverse, associativity, triangle-inequality, permutation-preservation, generic) emitted `inputs={}`, which always fell through `_format_pytest`/`_format_jest`'s "no inputs" branch to a bare `pass`/`TODO` body — i.e. every metamorphic test ever generated was a no-op, not just the symmetry case STUBS.md called out by name. Rewrote to generate concrete, type-sampled inputs (`_sample_value`) plus a `relation` tag that the formatters use to emit a real assertion reflecting the actual mathematical property (e.g. symmetry → `assert f(a, b) == f(b, a)`). Verified end-to-end: generated tests genuinely pass against a correct implementation and genuinely fail against a broken one (confirmed by real pytest execution, not just code review). Two relations ("inverse", "generic") can't be turned into a real equality check from function metadata alone and now get an honestly-labeled smoke test instead of a fabricated assertion.
- `_format_value()`: always emitted Python literals (`None`/`True`/`False`) regardless of target language — invalid JavaScript for every Jest test containing a `None`/boolean input or expected output. Now language-aware (`null`/`true`/`false` for `"javascript"`).
- `run_tests()`: always returned `{"passed": 0, "failed": 0, ...}` regardless of whether pytest/jest were installed or whether the tests would actually pass. Now really invokes pytest (Python) or Jest (JavaScript) as a subprocess and parses real pass/fail/error counts, degrading honestly (matching the tool-availability convention already used by `rust_debug`/`cpp_debug`) when the runner isn't available.
- `measure_coverage()`: always returned `{"line_coverage": 0.0, "branch_coverage": 0.0}`. Now really invokes `coverage.py` (Python) or `jest --coverage` (JavaScript). The JS path required discovering, by direct testing rather than assumption, that Jest's coverage instrumentation never tracks the test file itself even with `collectCoverageFrom` pointed at it — source and test must be separate files with a `require()` between them, so the fix writes the source to its own module and auto-generates a `module.exports` listing its top-level function declarations.
- `run_fuzzing()`: `"coverage_estimate": 0.75` was a hardcoded constant returned regardless of the code passed in. Now takes an optional `existing_test_code` param; when supplied, `coverage_estimate` is a real measurement via the fixed `measure_coverage()` (and `uncovered_conditions` is filtered to constructs whose real line range actually shows up in measured missing lines, rather than listing every branch-like construct unconditionally). Without existing test code, `coverage_estimate` is honestly `None` rather than a fabricated number.
- The general test-body generator's zero-input fallback (fired whenever a test case had no inputs to vary, e.g. a zero-parameter function) emitted literal `# TODO: Implement test` / `pass` (or the JS equivalent) directly into generated output — a "generated test" that was actually an empty stub. Now emits a real (if minimal) smoke-test call instead, honestly labeled as checking only that the call doesn't raise.

15 new tests (`test_generator/tests/test_stub_fixes.py`), including tests that actually run generated code through real pytest/coverage.py to confirm the fixes work end-to-end, not just that they return non-placeholder values.

**`troubleshooting/diagnostics.py` — decision recorded (implement, not delete), all three classes fixed:**
- `UniversalTroubleshooter._suggest_fixes()` ignored its `state` argument entirely and always returned the identical `{"cause": "Unknown error", ..., "confidence": 0.7}`. Now branches on a real classification (missing-dependency, permission, input, performance, resource, import, or unclassified error) with distinct, actionable suggestions and confidence per category.
- `ToolDiagnostician.diagnose_pyprover_failure()` always returned `{"suggestions": ["Simplify code"]}` regardless of the actual exception. Now inspects the exception type/message (`NotImplementedError`, missing `z3-solver`, `TimeoutError`, `SyntaxError`, or unrecognized) and gives a targeted diagnosis per case.
- `HealthChecker.check_all_tools()` was hardcoded to report every component `"healthy"` unconditionally, structurally incapable of ever reporting a real problem. Now really probes each component's actual external dependencies (rustc/clippy/clang via `shutil.which`+subprocess, z3-solver/hypothesis/pytest/coverage.py/jest via `importlib`/`shutil.which`) and reports `"degraded"` when a dependency is genuinely missing — confirmed to actually change output in this sandbox (`master_debugger` reports `"degraded"` here, since rustc/clang aren't installed).

These three classes were also previously dead code — nothing in the suite imported `diagnostics.py` directly, only `troubleshooting/__init__.py`'s separate `phases_5.py` implementation — meaning a direct import got fake results with no signal they were fake. Now exported from `troubleshooting/__init__.py` (and from the top-level `src/__init__.py`) alongside `Troubleshooter`, so they're reachable through the supported path. 9 new tests (`troubleshooting/tests/test_diagnostics.py`).

**`javascript_debug/__init__.py` — `JavaScriptDebugger.execute_with_debug()`/`analyze_patterns()`:** both were a bare `pass` (returning `None` regardless of input), even though the JS they wrap (`debug-engine.js`, 463 lines; `bug-patterns.js`) is real and substantial — this Python orchestration class was the one thing a caller would actually instantiate, and it did nothing. Replaced with a real Node.js subprocess invocation. Fixing this surfaced two real, 100%-reproducible bugs in `debug-engine.js` itself that the previous stub had made unreachable: `instrumentCode()`'s single global regex opened a call to `logVariable()` for every `let`/`const`/`var` declaration but never closed it (syntax error on every single instrumented declaration), and `logVariable()` had no `return value` statement, so — after fixing the syntax error — every instrumented variable was silently rebound to `undefined` regardless of its real value. Fixed `instrumentCode()` with a real statement-end scanner (tracks bracket/string/template-literal depth so semicolons inside a string or nested call don't terminate the statement early) instead of a naive regex, and added the missing `return value`. The previous test file (`javascript_debug/tests/test_execution_tracing.py`) would not have caught any of this: several of its 6 tests asserted tautologies (`assert all(field in expected_fields for field in expected_fields)`, `assert len(expected_patterns) == 10`) that pass regardless of product behavior, and three were a bare `pass` body checking nothing. Rewritten to actually invoke Node and check real output; 9 tests now (net +3), skipped honestly via `pytestmark` when `node` isn't on PATH rather than failing.

### Version-string drift reconciled

`src/__init__.py` (`2.6.1`), `INTEROP.yaml` (`1.2.0`), and `MANIFEST.txt` (`2.6.1`) all disagreed with `CHANGELOG.md`/`SKILL.md`'s accurate `2.9.4`. All four (plus `SKILL.md`) bumped together to `2.9.5` in this pass, along with the test-count claims in `MANIFEST.txt`/`SKILL.md` (371 → 424, reflecting the 41 new tests added while fixing the items above).

### Test suite

427 passed, 57 skipped, 1 deselected, 0 failed (383 baseline this session started from + 17 rust_debug/static_analyzer + 15 test_generator/stub_fixes + 9 troubleshooting/diagnostics + 3 net new in javascript_debug/test_execution_tracing (6 tautological/no-op tests replaced with 9 real ones) = 427, zero regressions).

## [2.9.4] - 2026-07-10 (two severe synthesis bugs found in the bug-detection tool's own aggregation logic)

### Fixed

Found while investigating roadmap.md §5's flagged-but-not-yet-built "conflict resolution when streams disagree" item. Before building that as new functionality, tested whether the orchestrator's *existing* synthesis logic was even structurally capable of surfacing a disagreement — it wasn't, for two independent reasons, both confirmed by direct execution before any fix was written.

**Bug 1 (`src/python_debug/bug_patterns.py`):** `BugPatternDetector`'s exception-driven dispatch recognized exactly four exception types (`IndexError`, `KeyError`, `TypeError`, `ZeroDivisionError`). Any other unhandled exception fell through with zero patterns generated, even though `report.exception_info` correctly captured the real crash. Confirmed directly: a bare undefined-name reference inside a function body raised `NameError`, `exception_info` captured it correctly, and `Phase1RuntimeDebug.run()`'s `passed = len(patterns) == 0` reported `passed=True` — a function that crashes on every call, reported as passing. Fixed with a new `UNHANDLED_EXCEPTION` fallback pattern covering every exception type without a specialized detector.

**Bug 2 (`src/master_debugger/orchestrator.py`):** `report.issues_found` — the list the final synthesis logic actually reads to decide whether to report "✅ VERIFIED" — only ever received async-concurrency findings. Static analysis (`mypy_errors`/`pylint_issues`) and runtime findings (`patterns_found`) were counted into local integer variables and then discarded; they never became `Issue` objects, never reached `report.issues_found`. Combined with Bug 1 being fixed, this was directly confirmed: code with a real captured `NameError` alongside a trivially-passing formal contract produced `"✅ VERIFIED"` / `RiskLevel.LOW`. Fixed two ways: static/runtime findings are now converted into real `Issue` objects and appended to `report.issues_found`; and the synthesis logic was restructured to check `total_issues` and `pyprover_verified` independently rather than letting a passing formal check short-circuit past everything else. When both disagree (issues found elsewhere *and* PyProver reports verified), the report now surfaces an explicit `"⚠️ CONFLICT: formal verification passed but N static/runtime issue(s) were found elsewhere"` state — this is the "streams disagree" conflict-resolution behavior roadmap.md §5 flagged as missing from `master-debugger v3.0`'s blind-spot model, arrived at by fixing the orchestrator's own real bug rather than porting v3.0's documentation-only version of the concept.

A real bug was found and fixed while writing this fix's own tests, not just at the end: the first version of the runtime-Issue conversion compared `pattern_name == "unhandled_exception"` to assign severity, but `RuntimeDebugResult.patterns_found` is typed `List[str]` while `Phase1RuntimeDebug.run()` actually stores the `BugPatternType` enum members themselves (a pre-existing, separate minor type/hint mismatch) — so that comparison was silently always `False`, and every runtime pattern including unhandled exceptions would have gotten `severity="medium"`. Caught by a test asserting the specific severity value, not just presence; fixed by normalizing to `.value` before comparing or storing.

**Separately noted, not fixed:** `ContractVerifier.verify_contract()` reports `verified: True` vacuously for code with zero `# Pre:`/`# Post:` annotations at all ("nothing was checked" reported identically to "checked and correct"). This is arguably standard/defensible vacuous-truth behavior for a lightweight contract checker, not a bug introduced or found broken here — but it does mean the new CONFLICT state can now fire even when PyProver's stream found nothing to disagree *about*, which is intentional (a vacuous pass shouldn't silently outrank a real crash) but worth knowing about when reading a CONFLICT report. See roadmap.md §20.3.

### Test suite

11 new tests: `python_debug/tests/test_unhandled_exception_pattern.py` (6), `master_debugger/tests/test_synthesis_conflict_resolution.py` (5, covering all four synthesis outcomes: clean-verified, conflict-with-vacuous-pyprover-pass, conflict-with-genuine-pyprover-pass, and issues-found-with-no-disagreement). Observed locally: 391 passed, 57 skipped, 1 deselected, 0 failed (380 + 11, zero regressions).

## [2.9.3] - 2026-07-10 (`len()`/`abs()`/`min()`/`max()` and string predicates — the biggest silent gap found so far)

### Added

Found by direct testing rather than a version comparison this time: none of the three independent `_expr_to_z3()` implementations in this fork (`contract_verifier.py`, `loop_verifier.py`, `contract_simplifier.py`) handled `ast.Call` at all. Confirmed before writing anything: `# Pre: len(arr) > 0`, `# Post: abs(result) >= 0`, `# Post: result == max(a, b)`, and `# Pre: s == "hello"` all silently degraded to `"non-arithmetic — skipped"` — not an error, not a warning, just quietly unverified. This is very likely the single highest-impact gap in the verifier: `len()` in particular is probably the most common function call in real contracts, and a contract full of `len()`/`abs()`/string checks was verifying "successfully" while checking close to nothing.

**New module: `src/pyprover/z3_builtins.py`**, shared Call-node support across all three `_expr_to_z3` call sites (each still independently defined, per `contract_verifier.py`'s existing "avoid circular imports" convention — this module takes the caller's own `_expr_to_z3` as a parameter rather than importing one):

- `len(x)`, `abs(x)`, `min(a, b, ...)`, `max(a, b, ...)` — real Z3 arithmetic. `len(x)` is modeled as a stable per-argument-text Z3 Int (repeated `len(arr)` calls within one verification share the same variable); `abs`/`min`/`max` recurse into arbitrary sub-expressions via the caller's translator, not just bare names.
- `str_length(s)`, `str_equals(a, b)`, `str_contains(s, sub)`, `str_starts_with(s, prefix)`, `str_ends_with(s, suffix)` — backed by Z3's **real native String theory** (`z3.Length`/`z3.Contains`/`z3.PrefixOf`/`z3.SuffixOf`), not a port of PyProver v6.1/v7.0's `StringWorkAround` integer-encoding hack. Those versions hand-rolled character-scaling into ints because they weren't using Z3's real string theory; z3-solver has had native string support for years, so this restores the *capability* those old versions were reaching for without reintroducing their workaround. Bare string comparison (`s == "hello"`) also now works, via a new textual pre-pass (`infer_string_names()`/`seed_string_env()`) that types a free variable as `z3.String` instead of the default `z3.Int` when it's directly compared to a string literal or passed to one of the `str_*` predicates — deliberately conservative (only a clear signal flips the type; anything ambiguous stays the safe-to-be-wrong-in default `Int`, which fails cleanly via the existing skip path rather than misverifying).

**Explicitly not done, and why:** float precision / scaled-integer float reasoning (v6.1/v7.0's `FloatWorkAround`). Z3 has real `Real`/`FP` sorts, same story as strings above — but wiring a second alternate sort through three call sites that all assume bare names default to `Int` needs the same kind of type-inference pre-pass built for strings here, for a different sort with different comparison-operator implications, and is a separately-scoped follow-up, not attempted this pass. See `roadmap.md` §19.

### Test suite

30 new tests: `test_z3_builtins.py` (21 — real Z3 semantics for every builtin, the string-typing inference pre-pass, and the unsupported-function/method-call/wrong-arg-count boundary), plus 9 integration tests in `test_verification.py`'s new `TestBuiltinFunctionContracts` class proving both the positive case (verified) and negative case (a real contradiction actually caught, not just "didn't crash") for every builtin through `ContractVerifier.verify_contract()` end-to-end. Observed locally: 380 passed, 57 skipped, 1 deselected, 0 failed (350 + 30, zero regressions).

## [2.9.2] - 2026-07-10 (real quantifier support and ghost state tracking; loop_verifier integration explicitly deferred)

### Added

Two features found missing during a cross-version comparison and confirmed absent by direct inspection (`grep -rl "forall\|ghost\|quantifier" src/pyprover/*.py` before starting — the only hit was a hardcoded string literal in `types_phase3.py`, never parsed or passed to Z3). See `roadmap.md` §18 for the full investigation, including why every prior version's "quantifier support" across all three branches turned out to be either a hardcoded template or a regex match that discarded the quantified condition — this is the first real implementation.

**New module: `src/pyprover/quantifiers.py`** — real `forall`/`exists` support over the `all(cond for i in range(...))`/`any(...)` syntax already used elsewhere in this codebase. Two strategies chosen automatically: bounded unroll (small integer-literal bounds, each instance checked individually so violations report a real counterexample like `i = 5`, not an empty model) and native `z3.ForAll`/`z3.Exists` (symbolic or large bounds). Wired into `contract_verifier.py`'s `_clause_to_z3()`, so `# Post: all(i >= 0 for i in range(0, n))` now goes through real quantifier checking instead of the old regex stand-in.

**New module: `src/pyprover/ghost_state.py`** — `# Ghost: name = expr` / `# GhostUpdate: name = expr` comment annotations (same convention as the existing `# Pre:`/`# Post:`/`# Inv:` scanning) for spec-only auxiliary variables, checked for real Z3 consistency against declared updates and, when supplied, actual real-variable constraints. Reports which mode ran (weak self-consistency vs. the stronger real-constraints check) rather than overclaiming.

**Deliberately not done:** `loop_verifier.py`'s INIT/PRESERVATION invariant checker was not wired to `quantifiers.py`. PRESERVATION requires induction (the invariant must hold again after an arbitrary iteration step), and `check_quantifier()` only proves a quantified statement true at a single state — reusing it naively would report a real-looking "verified" for something weaker than what PRESERVATION is supposed to mean. Confirmed the current behavior degrades safely instead: a quantified invariant hits `NotImplementedError` in the existing AST translator and is caught and reported as `skipped=True`, never a false "verified". Full scope of the real fix is in `roadmap.md` §18.2.

### Two real bugs found and fixed while building, not just at the end

1. `GhostStateTracker.check_consistency()` returned `verified` for a `GhostUpdate` referencing an undeclared ghost variable whenever `declarations` was empty — the early-return only checked `declarations`, not `updates`, so the undeclared-reference check below it was unreachable in that case. Fixed: the early-return now requires both lists to be empty.
2. The same method's docstring claimed results were "jointly satisfiable with real-variable constraints" when no such constraints were ever actually threaded into the solver anywhere in the call chain — only variable *names* were being passed in, not constraints on them. Fixed by adding an explicit `real_var_constraints` parameter and reporting which check actually ran (weak vs. strong) in the result's `detail` field, rather than silently overclaiming the stronger one.

### Test suite

28 new tests: `test_quantifiers.py` (14), `test_ghost_state.py` (11), plus 3 integration tests in `test_verification.py`'s new `TestQuantifiedContracts` class. Observed locally: 350 passed, 57 skipped, 1 deselected, 0 failed (322 + 28, zero regressions) — see roadmap.md §18.3 for a noted discrepancy against §17.4's previously-recorded "371 passed" baseline (environment difference, not re-derived this session, stated rather than silently reconciled).

## [2.9.1] - 2026-07-10 (two real stubs found via body-diff; a merge-methodology gap disclosed)

### Fixed

Prompted by re-reading the sibling v2.5.2 branch's own conversation summary (chat `3abe64d4-9daa-44e5-acc8-5e4e6cda9f6b`), which mentioned two stub-elimination fixes (`MasterDebugger.classify_risk()`, `RustDebugger.phase_2_formal()`) that v2.8.0's merge of that same archive never checked for. v2.8.0 only diffed function/class **names** present in each branch (the same method used for the six-archive audit in §13) — a function that exists with the *same name* in both branches but a stub body in one is invisible to a name-presence check. Running a full `diff` on every shared file (not just comparing which names exist) against the real archive caught both:

- **`master_debugger/orchestrator.py`'s `MasterDebugger.classify_risk()`** (the v6 orchestrator's async risk classifier) was hardcoded to return `{"risk_level": "medium", "score": 0.5, ...}` for every input, regardless of what the code actually contained. Replaced with the real pattern-based classifier from the sibling archive: four risk bands (CRITICAL/HIGH/MEDIUM/LOW) driven by real indicator matching (`eval(`, `os.system(`, `pickle.loads`, etc. for CRITICAL; file I/O, network, concurrency, and complexity metrics for HIGH; and so on), returning genuinely different scores and risk levels for genuinely different code. Verified directly: trivial code → `low`/0.1, `eval(user_input)` → `critical`/1.0 with the matched factor named, moderately branching code → `high`. A hardcoded classifier is a worse failure mode than an obviously-broken one — it looks like a real signal while silently ignoring the input entirely.
- **`rust_debug/phases.py`'s `RustDebugger.phase_2_formal()`** was a placeholder: a docstring claiming it delegates to PyProver, followed by `# Placeholder - would call PyProver bridge` and an unconditional `return None`. Replaced with the real implementation: delegates to `PyProverBridge.verify()` when available, falls back to the local `ContractVerifier` directly (parsing `// Pre:`/`// Post:` annotations) when the bridge isn't, and returns `None` only when there's genuinely nothing to verify. This particular merge was not a wholesale file replacement — the rest of `rust_debug/phases.py` (tool-availability-aware confidence scoring, honest degradation messaging for partial rustc/clippy availability) is this branch's own, more advanced work that the sibling archive lacks; only the `phase_2_formal` method itself was replaced, surgically, keeping everything around it.

**What this means for the six-archive audit in §13 and the CHANGELOG's own v2.8.0 entry:** both used the same name-presence-only diffing method used here for `master_debugger/phases.py`/`c_debug`/`cpp_debug` (which turned out fine on manual body-inspection this session) and are very likely fine for the same reason those turned out fine — but "very likely fine" is a weaker claim than what those sections stated. **Not re-auditing the other six archives with a full body-diff this session** — that's real, bounded, explicitly-scoped follow-up work, not attempted here; flagged honestly rather than silently left implied-complete. See roadmap.md §17 for detail and the specific recommendation.

### Test suite

7 new regression tests: `TestMasterDebuggerV6ClassifyRisk` (4 tests, `test_orchestration.py`) and a new `src/rust_debug/tests/` directory (`test_phase_2_formal.py`, 3 tests) — `rust_debug` had no test coverage at all before this release; broader coverage of the rest of that module remains a separate, pre-existing gap. Full suite: 371 passed, 57 skipped, 1 deselected, 0 failed (364 + 7, zero regressions).

## [2.9.0] - 2026-07-10 (`EquivalenceVerifier` — real code-to-code equivalence)

### Added

Direct response to a gap the v2.8.0 documentation pass explicitly named: Max asked whether `ContractSimplifier` proves that verbose code can be simplified to equivalent code with the same result — it doesn't, and that entry's own clarification said so. This release builds the thing that actually does.

**New module: `src/pyprover/equivalence_verifier.py`**

- `verify_expression_equivalence(expr_a, expr_b)` / `verify_function_equivalence(code_a, func_a, code_b, func_b)`: symbolically execute both inputs over shared Z3 variables and prove their outputs equal for all inputs (negate equality, check UNSAT), or return a concrete counterexample. Supported subset: straight-line and branching integer/boolean arithmetic (reuses `contract_verifier.py`'s `_expr_to_z3` — not reimplemented), plus `for x in range(N)` loops with a literal `N`, bounded-unrolled up to `max_unroll` (default 64) — same principle as this suite's existing CBMC/KLEE bounded model checking. Explicitly out of scope, stated in the module's own docstring before any code: general program-equivalence checking is undecidable for Turing-complete languages (Rice's theorem) — this is not that, and doesn't claim to be.
- `simplify_function(code, func_name)`: builds the same symbolic Z3 expression for a function's return value and hands it to `z3.simplify()` — Z3's own sound term-rewriting engine. The result is a genuine algebraic simplification of what the code computes (e.g. a redundant nested `if` collapsing to a single comparison), not a paraphrase.
- `propose_redundant_branch_removal(code, func_name)`: exactly one hand-written rewrite pattern (`if cond: return X else: return X` → `return X`) — deliberately not an open-ended search or a general synthesis engine. Every candidate it proposes is run back through `verify_function_equivalence()` before being returned; nothing is ever surfaced as "equivalent" on pattern-match confidence alone.
- Everything out-of-scope (function calls, recursion, list/dict/string ops, generators, unbounded loops, a bare boolean-typed variable used directly with `and`/`or`/`not`) raises `UnsupportedConstructError` or degrades to `status="unsupported"` with a specific reason — never a silent wrong answer in either direction (never a false "equivalent", never a false "not equivalent").

**Bridge wiring:** `PyProverBridge.verify_equivalence()` and `.simplify_function_code()`, following the existing `verify_ffi()`/loop-verification method pattern — return `None` only when PyProver itself is unavailable, distinct from `status="unsupported"` for a specific unanalyzable construct.

**Two real bugs found and fixed during development, not just disclosed at the end:**
1. The first control-flow implementation rejected the ordinary "early return" pattern (`if cond: return X` followed by more code) as "ambiguous control flow" — this is actually the single most common branching pattern in real code, and the rejection was overly conservative, not a genuine ambiguity. Rewrote the statement-execution logic with an explicit `("return", value)` / `("fallthrough", env)` flow representation that correctly threads the non-returning branch into the remaining statements. Regression test added (`test_early_return_pattern_supported`, plus the mirror-image case).
2. The reused `contract_verifier._expr_to_z3` raises a raw `NotImplementedError` for unsupported AST nodes (function calls, attribute access) — the new module wasn't catching this at every call site, so it could crash instead of degrading to `status="unsupported"`. Fixed with a wrapper (`_expr_to_z3_safe`) applied uniformly. Separately, expressions with a bare boolean-typed free variable (e.g. `not a` where `a` is meant as a boolean) hit a genuine inherited scope limit — the translator always seeds unbound names as Z3 `Int`, so `Not()` on one is a sort-mismatch `Z3Exception` — now caught and reported with an explanatory workaround (use an Int-typed comparison like `a > 0`) instead of crashing.

**Test suite:** 32 new tests (28 in `test_equivalence_verifier.py`, 4 in `test_pyprover_bridge.py`'s new `TestVerifyEquivalenceBridge`/`TestSimplifyFunctionCodeBridge`). Full suite: 364 passed, 57 skipped, 1 deselected, 0 failed (332 + 32, zero regressions).

### Documentation

- `SKILL.md`: new `EquivalenceVerifier` component entry, a matching "EquivalenceVerifier scope" note (same pattern as `LoopVerifier scope`/`ContractSimplifier scope`), and the v2.8.0 "what ContractSimplifier does NOT do" note updated to point at this new module instead of saying the capability doesn't exist.

## [2.8.0] - 2026-07-10 (real `ContractVerifier`, from the actual sibling v2.5.2 archive)

Max uploaded the actual `debug-suite.skill` v2.5.2 archive (the sibling branch this project reconciled with via `conversation_search` transcripts in the v2.7.0 entry below — this is the real file, not snippets). Audited it in full against the v2.7.0 package below using the same function/class-presence sweep as the six-archive audit (roadmap.md §13.1's method). Confirms the earlier `conversation_search`-based reconciliation was accurate — `master_debugger/__init__.py`, `pyprover_bridge.py`'s `_map_language_type`, and `requirements.txt` are all byte-for-byte identical to what v2.7.0 already has. Two real, substantive findings:

### Fixed — `pyprover/contract_verifier.py` was a non-functional stub; replaced with sibling's real implementation

`src/pyprover/contract_verifier.py::ContractVerifier.verify_contract()` — the actual entry point every `verify_contract()` call in this suite goes through — was a 154-line stub whose own comment admitted "Full Z3 verification would require sophisticated SMT setup." It never called `Solver.add()` on a parsed postcondition; it just checked whether precondition/postcondition lists were non-empty. This was known and documented (roadmap.md §12.1/§13.4), but its scope wasn't fully appreciated until this comparison: **the existing test suite's `TestContractVerification`/`TestVerificationEdgeCases`/`TestContractParsing` classes were passing against this stub the whole time**, because their assertions are vacuous against any non-crashing implementation - e.g. `assert result.get('verified') is True or result is not None` is true for literally any dict. Confirmed by direct testing before replacing: a contract with a precondition that provably does *not* imply its postcondition (`# Pre: x > 0` / `# Post: x > 100`) reported `verified: True` against the stub.

Replaced wholesale with the sibling v2.5.2 archive's real `contract_verifier.py`: genuine `ast`-based (no `eval()`) comment-annotation parsing (`# Pre:`/`# Post:`/`# Inv:`, also `//` and `/* */` forms), real Z3 checks for precondition satisfiability, postcondition **validity** (implication-checked via negate+UNSAT for clauses that don't reference the function's return value; satisfiability-only, by explicit documented design, for clauses that do reference `result`/`return`/`retval`/`ret`/`output`, since the actual return expression isn't evaluated here), and invariant satisfiability. Includes its own input-size hardening (`MAX_CONTRACT_INPUT_CHARS`, `MAX_CONTRACT_LINES`, `ContractInputTooLargeError`) and its own `_is_z3_bool` bare-identifier guard (same pattern independently applied in this session's earlier `contract_simplifier.py` fix).

Re-verified after replacing: the false-positive case above now correctly reports `verified: False` with a Z3 counterexample (`x = 1`); a genuinely-provable case (`# Pre: x > 100` / `# Post: x > 0`) still reports `verified: True` with "implied by preconditions"; full suite (332 tests, including the existing - now meaningfully exercised - `ContractVerifier` test classes) still passes; end-to-end through `PyProverBridge.verify()` correctly classifies the false-positive case as `RiskLevel.CRITICAL` with the real counterexample in the summary.

**Bidirectional gap, not a one-way merge:** the sibling's `contract_verifier.py` does *not* have this session's earlier `contract_simplifier.py` bare-identifier fix (§ v2.7.0 entry below) - confirmed by diff, sibling's `contract_simplifier.py` is unpatched. That fix is preserved; only `contract_verifier.py` was replaced.

### Updated

- `SKILL.md`'s PyProver capability description now accurately reflects real implication-checking, not just satisfiability.
- `legacy_code/pyprover_v11_adapters/FINDINGS.md`'s comparison point (this project's own correctly-implemented implication-checking) now includes the real `contract_verifier.py`, not just `contract_simplifier.py`/`loop_verifier.py`.

### Test suite

332 passed, 57 skipped, 1 deselected, 0 failed — same count as v2.7.0 (this was a same-file replacement + doc updates, no new test files; the value here is that the existing 332 include meaningfully-exercised `ContractVerifier` tests now, not that the count changed).

## [2.7.0] - 2026-07-10 (branch reconciliation)

### Fixed — merged in from sibling v2.5.2 branch

This branch (v2.6.1) and a sibling branch (v2.5.2, chat `3abe64d4-9daa-44e5-acc8-5e4e6cda9f6b`) diverged from the same common ancestor at nearly the same timestamp, each unaware of the other. Neither branch's version number was authoritative over the other — this release is an actual diff-and-merge, not a pick-one. See `debug-suite-handoff.md`'s "Known Risks" section (superseded by this entry) for the full divergence table.

- **`master_debugger/__init__.py` now exports both orchestrators.** Previously only `MasterDebuggerV5` (legacy, pattern-matching-only `classify_risk()`) was exported; `MasterDebugger` (v6, the more capable orchestrator that directly integrates `RustDebugger`/`CppDebugger`/`PyProverBridge`) was dead code, unimported anywhere. The sibling branch already made this call — export it — and this reconciliation honors that decision rather than re-litigating it. `__version__` bumped to `"6.0.0"` to reflect v6 now being the active, reachable orchestrator.
- **`common/pyprover_bridge.py`'s `_map_language_type` now accepts a `LanguageType` enum directly**, not just a raw lowercase string, returning it unchanged. Previously any caller already holding a `LanguageType` (rather than a PyProver-format string) would crash on `.lower()`, since enum members aren't strings.
- **`requirements.txt`: removed `hypothesis` as a phantom dependency.** Declared but never imported anywhere in `src/`, confirmed by `grep -rln "import hypothesis" src/` returning nothing both in the sibling branch and independently re-confirmed here. Left as a commented-out future dependency note for `HypothesisIntegrator` (roadmap §3, not yet built).
- **Same underlying bug class as the sibling's `contract_verifier.py` fix, found independently in this branch's actual live code path (`pyprover/contract_simplifier.py`'s `_implies`/`_is_tautology`).** The two branches' `src/pyprover/contract_verifier.py` are structurally different — this branch's is a 154-line stub (`"Full Z3 verification would require sophisticated SMT setup"`) that never calls `Solver.add()` on a parsed postcondition at all, so the sibling's literal patch doesn't apply here; the decorator-based `@requires`/`@ensures` contract system with real Z3 solving that the sibling patched isn't part of this branch's live `src/` tree (a prototype copy exists only in `legacy_code/`, not imported). The equivalent bug does exist here, though, in the file that actually does this branch's Z3 implication-checking: a bare-identifier clause (e.g. an `ensures` clause of just `"result"`, no comparison) parses via `_expr_to_z3`'s `ast.Name` branch to a Z3 `Int`, not a `Bool`; `_is_tautology`/`_implies` then called `z3.Not()`/`Solver.add()` directly on it and raised `Z3Exception: Value cannot be converted into a Z3 Boolean value`. Reproduced before fixing (`ContractSimplifier().simplify(requires=["n >= 0"], ensures=["result"])` crashed). Fixed with a new `_is_z3_bool()` sort-check guard: non-boolean clauses are now conservatively kept (not silently dropped, not crashed on) via the existing `unknown`/timeout-clause path. 4 new regression tests added (`test_bare_identifier_ensures_no_crash`, `test_bare_identifier_requires_no_crash`, `test_is_z3_bool_helper`, plus the existing suite unchanged).
- **Closed part of the "no dedicated integration tests for this session's new work" gap** flagged in `debug-suite-handoff.md`'s Test Strategy section: added `src/common/tests/test_pyprover_bridge.py` (4 tests, `_map_language_type` string/enum/case-insensitivity/unknown-input coverage) and `TestPublicAPIExports` in `master_debugger/tests/test_orchestration.py` (2 tests, confirms both orchestrators import and are in `__all__`). `SemgrepAnalyzer`/`LiefBinaryAnalyzer` dedicated integration tests remain an open gap — not addressed this release, scope was the branch-reconciliation fixes specifically.
- Full suite: 322 passed, 46 skipped, 1 deselected (up from 313 passed pre-reconciliation in this sandbox; the 9-test delta is exactly the new regression tests above; skip count reflects optional tools — rustc, clang, valgrind, etc. — not installed in this particular sandbox, not a branch difference).

### Also this release (same-day follow-up work, after initial reconciliation above)

- **`MasterDebuggerV5`'s `input()`-hangs-forever bug: fixed.** Design decision made (see roadmap.md §12.5 for full reasoning): `python_debug/debug_report.py`'s `execute_with_debug()` now defaults to `mock_stdin=True`, swapping `sys.stdin` for an empty buffer for the duration of `exec()` so any `input()` call fails instantly with `EOFError` instead of blocking forever — portable (unlike the pre-existing Unix-only `timeout_seconds` SIGALRM mechanism, which was never wired to a default anyway) and immediate (no waiting out a timeout). Restored in a `finally`, both on the crash and success paths. No call-site changes needed elsewhere — `Phase1RuntimeDebug.run()` already calls `execute_with_debug(code)` with defaults. 5 new regression tests (`TestStdinMocking` in `test_execution_tracing.py`). Verified end-to-end through the full `MasterDebuggerV5.debug()` path with real `input()`-calling code, each check guarded by an external subprocess timeout as a safety net.
- **`tree-sitter` integration: scoped and decided — no-go for a suite-wide integration.** Audited every regex-based source-parsing call site in `src/`. Finding: this suite's regex usage is either (a) tool-output parsing (Clang diagnostics, strace/valgrind output — not source grammars, tree-sitter doesn't apply) or (b) Python-source anti-pattern matching in `bug_patterns.py`, where the stdlib `ast` module (already used elsewhere in this codebase) is a better, dependency-free fit than adding tree-sitter. The suite's core languages (Rust, C, C++) already delegate to real toolchains (`rustc`+`clippy`, Clang Static Analyzer, CBMC/KLEE) — strictly better analysis than a syntax tree would provide. The one real gap (PyProver's language-agnostic comment-scanning contract parser for non-Python languages) is narrow and marginal, not the suite-wide framing originally implied. Full reasoning in roadmap.md §12.2.
- **`SemgrepAnalyzer`/`LiefBinaryAnalyzer` test gap closed** (flagged twice: handoff's Test Strategy section, and this file's own §12.3 above). Added `src/common/tests/test_semgrep_analyzer.py` and `src/cpp_debug/tests/test_lief_analyzer.py`, 9 tests total, following the existing skipif-gated integration-test pattern.
- **Six-archive feature-loss audit** (`pyprover-v8-2.skill`, `pyprover_v11_2.skill`, `pyprover_skill__2_.zip`, `python-debug_skill.zip`, `debug-suite-v2_2.skill`, `verification-debugging-suite-v1_1.skill`, all uploaded by Max). Full detail in roadmap.md §13. Headline results:
  - Both full-suite snapshots (v2.2, v1.1) and the filename-matching pyprover archive: **verified strict subset of current** — zero unintentional feature loss found across every module.
  - `pyprover_v11_2.skill`'s language-adapter system: **real source recovered**, superseding `legacy_code/LANGUAGE_ADAPTER_GUIDE_recovered.md` (which was an explicitly-marked-untested `conversation_search` reconstruction). Found and fixed a genuine **soundness bug** in its Z3 verifier (checked satisfiability instead of validity — a wrong postcondition like `@ensures("result < 0")` on a max-finder reported `verified: True` before the fix). Also found, documented, did not fix: its "10 verification templates" contribute zero real proof content (empty-stub constraint methods) even after the soundness fix. Not integrated into `src/pyprover/` this release — real source is now at `legacy_code/pyprover_v11_adapters/` (with `verifier_SOUNDNESS_FIXED.py` and a `FINDINGS.md`) for a properly-scoped future integration.
  - `pyprover-v8-2.skill`'s `core.py`: real per-template `generate_invariant()` logic that could fill the v11.2 template stubs above, archived at `legacy_code/pyprover_v8_2_core_with_real_template_invariants.py`, not integrated (needs a variable-binding-extraction bridge that exists in neither archive).
  - `python-debug_skill.zip`'s `conftest.py`: a genuine divergence (richer test fixtures/assertions than current's consolidated version) flagged for a human call, not merged automatically — see roadmap.md §13.6.

### Not merged / explicitly deferred (as of the reconciliation pass above; superseded by "Also this release" section for tree-sitter and the input() bug, both resolved same-day)

- `master_debugger/types.py` and `master_debugger/orchestrator.py`'s `RiskLevel` unification (this branch's own v2.6.1 work, importing from `common.interop` instead of three separate duplicate enum classes) was **not** touched by the sibling branch and is preserved as-is going into this merge — no conflict to resolve here, sibling simply didn't touch these files' `RiskLevel` handling.

## [2.6.1] - 2026-07-09 (same-day follow-up)

### Fixed

- **Unified the three separate `RiskLevel` enum classes** (`common.interop`, `master_debugger.types`, `master_debugger.orchestrator`) documented as a known issue in 2.6.0. `master_debugger/types.py` and `master_debugger/orchestrator.py` (dead code, unused but fixed for consistency) now both import `RiskLevel` from `common.interop` instead of redefining it. `src.RiskLevel` is now literally the same class object as `common.interop.RiskLevel` - `report.risk_level == src.RiskLevel.CRITICAL` now correctly returns `True` for reports from any component. One test's expected value updated (`test_critical_code_full_workflow`: `'critical'` → `'CRITICAL'`, the deliberate, verified consequence of the unification). 359/359 passing before and after.
- **`Phase0StaticAnalysis`'s bandit integration was silently broken - never actually surfaced a finding, on any input, ever.** `if 'WARNING' in output.stdout or 'SEVERITY' in output.stdout` doesn't match real bandit 1.9.4 output (`"Severity:"`/`"Issue:"`, never the all-caps strings checked for), and the `FileNotFoundError` fallback meant "bandit not installed" and "bandit found nothing" were indistinguishable. Same dormant-code pattern as the CBMC 6.x flag bug in 2.6.0. Fixed by switching to `bandit -f json` for structured parsing. Verified against real vulnerable code (hardcoded password + `shell=True` subprocess call): now correctly surfaces `B105`/`B404`/`B602` findings with severity and line numbers.

### Added

- **semgrep integration** into `Phase0StaticAnalysis` (`StaticAnalysisResult.semgrep_findings`, new `src/common/semgrep_analyzer.py`). Since `semgrep --config auto` requires network access to `semgrep.dev` (returns `HTTP 403` in this sandbox), a curated 20-rule security ruleset is bundled locally at `src/common/semgrep_rules/` (downloaded from `github.com/semgrep/semgrep-rules`, licensed under the Semgrep Rules License v1.0 - see `semgrep_rules/README.md`). Trimmed from the full 91-rule `python/lang/security/` set after measuring ~17s/scan at full size vs. ~6-7s/scan for the curated subset. Verified against real vulnerable code across 4 categories (unsafe pickle, weak MD5 hash, `eval()`, ReDoS), zero false positives on clean code.
- **Known tradeoff, disclosed not resolved:** semgrep adds a fixed ~6-8s to every `Phase0StaticAnalysis` call regardless of code size (subprocess startup + rule compilation dominate). This roughly 4-6x'd the pytest suite's total runtime (~10-17s → ~50-70s). Did not break anything (359/359 still passing) but is a real latency cost worth knowing about; not addressed this release.
- **lief integration** into `CppDebugger.debug()` (new `src/cpp_debug/lief_analyzer.py`, `LiefBinaryAnalyzer`/`lief_available()`). Analyzes the *compiled binary* rather than source: binary hardening posture (PIE/NX/RELRO/stack-canary) and dangerous-import detection (`system`, `strcpy`, `gets`, `sprintf`, ...) straight from the import table - a capability none of the existing source-level analyzers (Clang/CSA/cppcheck) have. Deliberately not a replacement for `pyelftools` in `dwarf_analyzer.py` (different purpose - lief doesn't have comparable DWARF-DIE depth for variable/type analysis). Only dangerous-import findings feed the automatic risk classifier by default (`include_hardening=False`); hardening-posture findings are a toolchain-constant property (fire on nearly any input regardless of code content) and are available via a direct `include_hardening=True` call instead, to avoid polluting per-code risk scoring with a signal that isn't about the code. Found and fixed a self-inflicted regression during verification (same pattern as the cppcheck `unmatchedSuppression` bug in 2.6.0): the `missing_stack_canary` finding, while accurate, fired on the formal test suite's trivial clean-code case too, regressing it from LOW to MEDIUM risk - resolved by the `include_hardening` split described above.

### Known issues (documented, not fixed)

- **`MasterDebuggerV5.debug()` can hang indefinitely** if traced code calls `input()` - Phase 1 genuinely executes the code (not purely static analysis), and there's no interactive stdin in sandboxed environments, so `input()` blocks forever. Found while testing the bandit fix against code that combined a security vulnerability with an `input()` call. See roadmap.md §11.9 for the reproduction and candidate fixes (none implemented - needs a design decision about execution semantics, not a quick patch).
- **`master_debugger/orchestrator.py`'s `MasterDebugger` class (module docstring: "Master-Debugger v6") is dead code** - not imported anywhere in `src/` or `tests/`, discovered while tracing `RiskLevel` usages for the unification fix above. It directly integrates `RustDebugger`/`CppDebugger`/`PyProverBridge` (more capable than the exported `MasterDebuggerV5`'s pattern-matching-only `classify_risk()`), and has its own third `UnifiedDebugReport`/`Issue` dataclasses distinct from `common.interop`'s. Whether this should replace, merge with, or stay separate from `MasterDebuggerV5` is a real architecture question for a future session, not decided here. See roadmap.md §11.7.

### Test Suite

- Full suite: **359/359 passing** throughout (verified after the RiskLevel unification and again after the bandit/semgrep changes - same count both times, no regressions).

## [2.6.0] - 2026-07-09

### Fixed

- **`src/__init__.py` was completely empty (0 bytes).** The v2.5.0 archive shipped real, working code for `assembly_debug`, `c_debug`, `cpp_debug`, `rust_debug`, but the root package `__init__.py` - the single-import public API surface - had no content at all: no `from src.master_debugger... import MasterDebuggerV5`, no `__all__`, no `__version__`. Rebuilt from the v1.0.0 file, extended with every v2.5.0 addition (54 exports), verified by `import src` + `hasattr` check on every `__all__` name, not just import success. See roadmap.md §11.1.
- **`src.test_generator` package import was broken since v1.0.0 and never actually ran.** The old `__init__.py` tried `from src.test_generator import TestGenerator, generate_tests, TestCase, TestGenerationResult`, but `test_generator/__init__.py` only ever re-exported `TestGenerator`. Fixed by importing the other three from the submodule directly.
- **`RustDebugger.debug()` reported false confidence (0.95, "✅ No violations") when rustc/clippy weren't installed at all**, indistinguishable from a genuinely clean result. `phases_executed` was also hardcoded to `["static", "runtime"]` regardless of what actually ran. Now checks `rustc_available`/`clippy_available` (already tracked internally by `BorrowCheckerParser`/`ClippyLinter`, just never read by `debug()`), reports `confidence_score=0.0` and an explicit warning when neither tool ran, `0.4` when only one ran, and only the phases that actually executed in `phases_executed`. Verified against real installed rustc/cargo/clippy (apt) in all three states: neither/one/both tools present, including a real caught borrow-checker violation. See roadmap.md §11.3.
- **CBMC 6.x flag incompatibility silently disabled all CBMC checking.** `CBMCDriver.BASE_FLAGS` used `--null-pointer-check`/`--overflow-check`, which CBMC 6.x renamed/split to `--pointer-check`/`--signed-overflow-check`+`--unsigned-overflow-check`. CBMC 6.x treats the old names as a hard usage error and runs *zero* checks, printing help text instead - which `_parse_cbmc_output` correctly parsed as "zero findings," making every CBMC run on 6.x indistinguishable from "checked, found nothing." Caught by actually installing CBMC 6.10.0 and running the existing (previously never-exercised-in-CI-with-a-real-toolchain) `TestCBMCIntegration::test_div_zero_detected` test. Fixed flag names; verified a real division-by-zero is now caught. See roadmap.md §11.9.
- **`CppcheckAnalyzer`'s own `--suppress=missingIncludeSystem` flag produced a benign `unmatchedSuppression` meta-finding on trivial code**, which the existing risk classifier (`elif all_patterns: risk = MEDIUM`) counted the same as a real finding, regressing `test_debug_clean_code_low_risk` from LOW to MEDIUM. Fixed same-session by also suppressing `unmatchedSuppression`.
- **`rust_debug/setup.py` led with the `rustup.rs` curl-installer as the recommended install path**, which fails in sandboxed Claude environments without that domain allowlisted. Reordered to lead with `apt-get install -y rustc cargo rust-clippy` (verified working in this sandbox), rustup as an explicit fallback. Documented the `rust-clippy` (not `clippy`/`cargo-clippy`) Debian/Ubuntu package-name gotcha.

### Added

- **`ValgrindRunner`/`ValgrindReport`/`valgrind_available()`** in `src/c_debug/debugger.py`: dynamic memory-error detection (leaks, invalid read/write, invalid/double free, uninitialised-value use) via `valgrind --tool=memcheck`, wired into `CDebugger.debug()` alongside the existing strace tracer. Closes a real capability gap - previously `c_debug`/`cpp_debug` had static analysis + DWARF + syscall tracing but nothing instrumenting actual memory accesses at runtime. Verified against 4 real programs (leak, clean, heap overflow, double-free); one parser bug found and fixed during verification (see roadmap.md §11.4 for the `LEAK SUMMARY` false-positive detail).
- **`CppcheckAnalyzer`/`cppcheck_available()`** in new `src/cpp_debug/cppcheck_analyzer.py`: dataflow-based second-opinion static analyzer alongside Clang/CSA, wired into `CppDebugger.debug()` via the existing dedup/merge path. Uses cppcheck's `--xml` output for stable parsing rather than regex on human-readable text. Verified against a real leak, caught independently of (not duplicating) the CSA-derived finding for the same bug.
- Both new tools' install info added to their respective `REQUIRED_TOOLS`/`claude_check_and_install()` structures, following the existing pattern.

### Test Suite

- Full suite: **359/359 passing** (`python -m pytest tests/ src/ -q`), up from the last recorded 355/355 (v2.5.0) - +4 from newly-installed-and-exercised CBMC/cppcheck integration tests that were previously `skipif`-skipped in whatever environment last produced that number. This session's own ad-hoc smoke test (not part of `tests/`, used to verify this session's specific changes against real installed tools): 20/20 passing.

### Known issues (documented, not fixed this session)

- **Three separate `RiskLevel` enum classes** (`common.interop`, `master_debugger.types`, `master_debugger.orchestrator`) with identical-looking but non-interoperable values - `report.risk_level == src.RiskLevel.CRITICAL` silently returns `False` for any report from `RustDebugger`/`CppDebugger`/`CDebugger`/`AssemblyDebugger` even when genuinely critical, since those all use `common.interop.RiskLevel` while the top-level `src.RiskLevel` export is `master_debugger`'s. This is the same failure class the 2.2.2 entry below already partially fixed at one call site; the underlying duplication was never resolved. See roadmap.md §11.6 for the full writeup and a recommended fix.
- KLEE remains unavailable in sandboxed environments with no easy fix: no prebuilt binaries on any GitHub release, source-only, requires a patched LLVM + uclibc build. `klee_available()` already correctly reports this.

## [2.2.5] - 2026-06-30

### Fixed

- **SKILL.md frontmatter failed the official skill-creator validator.** `version`, `status`, and `interop_level` were top-level frontmatter keys; `scripts/quick_validate.py` (the actual upload-gating validator in `/mnt/skills/examples/skill-creator/`) only allows `name`, `description`, `license`, `allowed-tools`, `metadata`, `compatibility` at the top level - every prior `.skill` build in this CHANGELOG (2.2.0 through 2.2.4) would have been **rejected on upload** had it gone through the real validation path instead of being hand-zipped. Moved the three extra fields under a `metadata:` block, which the validator explicitly permits arbitrary nested keys under. Confirmed: `python quick_validate.py debug-suite` now reports "Skill is valid!"
- **MANIFEST.txt overclaimed "Zero production dependencies" and "100% Completeness"** while still listing v2.2.0 - stale since before the 2.2.0 cleanup pass. `requirements.txt` declares real dependencies (z3-solver is genuinely used by `verify_contract()`; hypothesis is a phantom dependency per roadmap.md §1). Corrected, and added `roadmap.md`/`legacy_code/` to the documentation-features checklist.

### Changed

- **Packaging now goes through the official `skill-creator` tooling** (`scripts.package_skill`, which runs `quick_validate.py` before zipping) instead of a hand-rolled `zip -r`. This also changes the on-disk zip layout: contents are now nested under a top-level `debug-suite/` folder (e.g. `debug-suite/SKILL.md`), matching the convention `quick_validate.py`/`package_skill.py` expect, rather than files sitting at the zip root as in 2.2.0-2.2.4's manual builds.
- Output filename is now `debug-suite.skill` (matching the `name:` frontmatter field and the skill-creator "preserve the original name" convention), not a version-suffixed filename. Version is tracked in `metadata.version` in the frontmatter and in this CHANGELOG, not in the filename.

### Test Suite

- Full suite: **160/160 passing**, unchanged from v2.2.4 - this release is packaging/validation/documentation only, no `src/` changes.

## [2.2.4] - 2026-06-30

### Added

- **`legacy_code/` folder:** Real, recovered-but-untested code fragments for the highest-value items in `roadmap.md`, pulled from conversation history via `conversation_search` rather than re-described from summaries. Includes: the v13.0 `loop_verifier.py` (INIT/STEP/TERM Hoare-logic loop invariant verification) and an even earlier prototype with the full symbolic-execution proof-obligation logic; the v13.1 `ContractSimplifier`/`ContractSimplificationResult` (redundant-clause removal via iterative Z3 implication checks); the Node.js/`acorn` subprocess fix for the JS parser's 10x speed problem; the multiline-`@requires(...)` contract extraction regex fix; and the `LanguageAdapter` 6-method interface + 10-template architecture from the v11.x multi-language adapter system. Every file is explicitly marked with what's missing (search snippets are partial, often truncated mid-function) and what `conversation_search` query would likely recover more - see `legacy_code/README.md` for the full index and usage instructions. This exists so a future restoration pass starts from recovered real code instead of re-discovering the same fragments from scratch.
- `roadmap.md` §0 and the relevant §2.1/§2.2/§2.3 tables now cross-reference which entries have a recovered fragment in `legacy_code/` and which don't.

## [2.2.3] - 2026-06-30

### Added

- **`roadmap.md`:** Comprehensive feature-restoration roadmap compiled from a full conversation-history search across every component skill merged into this suite (pyprover, python-debug, master-debugger, test-generator, code-orchestrator). Documents three divergent historical PyProver development branches (a library-integration branch reaching v7.0 with Coq/Lean export; a multi-language-adapter branch reaching v13.1 with loop verification, parallel verification, contract simplification, and a 5-layer CBMC/KLEE verification stack; and the branch actually merged into this suite, "v14.0," which is the most feature-poor of the three despite the highest version number). Flags that a prior "100% feature parity" completeness audit (in conversation history) is contradicted by direct code inspection - e.g. it claims Hypothesis property testing is "Complete," but `hypothesis` is a phantom dependency in `requirements.txt` never imported anywhere in `src/`. Includes a prioritized restoration order and a full index of 25 source chat links. Supersedes the C/C++/Assembly Phases 4-10 roadmap previously tracked only in an external document - that roadmap is now reproduced and kept current inside the package itself (§9), with Phase 4 marked done as of v2.2.0.

## [2.2.2] - 2026-06-30

### Context

Searched conversation history for the full lineage behind this suite's merged components (pyprover v6.1→v14.0, python-debug v11→v12.3, master-debugger v1→v6, standardize-skill). Found two categories of issues: (1) integration breakage between already-bundled components, and (2) a large feature gap between the bundled `src/pyprover` and the much more capable standalone PyProver versions developed in earlier sessions. Fixed (1) where contained; documented (2) as a backlog rather than attempting a risky partial port (see Known Limitations in SKILL.md).

### Fixed (component integration)

- **`master_debugger/orchestrator.py` `_phase_2_formal()` discarded every real PyProver result.** It read `result.verified`/`.template_type`/`.error` via `getattr(..., default)` on a `common.interop.UnifiedDebugReport`, which has no such attributes (it has `risk_level`, `confidence_score`, `summary`) - every `getattr` silently fell through to its default, so even after 2.2.1 fixed the bridge to return real verification results, the orchestrator was still discarding all of it and reporting "INCONCLUSIVE" or the wrong "verified" value (it was also comparing two *different* `RiskLevel` enums, the orchestrator's own lowercase-valued one vs. `common.interop`'s uppercase-valued one, which silently fail equality checks since they're different classes with different values). Now correctly derives `verified`/`error` from the report's real `risk_level`/`confidence_score`/`summary`.
- **`AsyncVerifier` (concurrency detection) was wired into `pyprover_bridge.verify_async()` in 2.2.1 but never connected to the orchestrator that actually drives analysis.** `master_debugger.debug_comprehensive()` now also runs `verify_async()` during the formal-verification phase and merges concurrency findings into `report.issues_found`; overall health/risk classification now accounts for them.
- **`AsyncVerifier.detect_concurrent_variables()` tokenized every word on every line of a file, including inside comments, docstrings, and string literals, and its "after await" flag was sticky for the rest of the file once set.** Dogfood-testing the newly-wired orchestrator against the suite's own `pyprover_bridge.py` (whose own docstrings discuss "await points") surfaced this immediately: it flagged ~150 tokens including English words like "the", "but", "no" as "concurrently-accessed variables." Now strips comments and single-line string literals before tokenizing, uses a 5-line window after each `await` instead of "rest of file forever," and filters Python keywords/common builtins from candidates.
- **Contract verification input hardening:** `ContractVerifier.parse_contract()`/`verify_contract()` had no bound on input size (the standalone PyProver v13.1's security-hardening pass added nesting-depth/injection protection that was never ported to this bundled, text-scanning version). Added a 200K-char / 20K-line input guard with an honest rejection result instead of an unbounded scan, plus null-byte stripping in extracted clauses.

### Fixed (dogfood testing: ran the suite's own master-debugger/python-debug against its own source)

- **`python_debug/debug_report.py`: every crash-report code path was broken.** `exception_info` is stored as a 6-key dict (`log_exception()`), but `get_execution_summary()` indexed it as `self.exception_info[0]`/`[1]` (a tuple access on a dict - `TypeError`/`KeyError`), and `_analyze_cause()`, `_generate_suggestions()`, `generate_human_readable()`, and `to_dict()` all did `exc_type, exc_value, _ = self.exception_info`, unpacking a 6-key dict as if it were a 3-tuple (`ValueError: too many values to unpack`). **Every one of these methods crashed on any input that actually raised an exception** - the suite's own crash-reporting feature could not report a crash. None of the existing 144 tests exercised these methods against a crashing program, so this had zero test coverage despite being on the most basic "debug a failing function" path. Fixed all 5 call sites to use dict-key access; added 7 regression tests (`TestCrashReporting`) that run real crashing code through every affected method.

### Test Suite

- Full suite: **160/160 passing** (`python -m pytest tests/ src/ -q`), up from 148 (12 new regression tests: 7 for the exception_info crash-reporting bug, 3 for async false-positive fixes, 2 for input hardening)

## [2.2.1] - 2026-06-30

### Fixed (continued Haiku 4.5 cleanup pass)

- **`src/pyprover/__init__.py` package import was completely broken:** `from .contract_verifier import ContractVerifier, verify_contract` imported a `verify_contract` name that doesn't exist in that module (only `ContractVerifier.verify_contract`, a staticmethod) - this raised `ImportError` on every `import pyprover`, silently caught and reduced to `__all__ = []`. The package has never actually been importable as a whole; only individual submodule imports worked.
- **`async_verifier.py`, `ffi_verifier.py`, `token_profiler.py` used absolute `from types_phase3 import (...)` instead of `from .types_phase3 import (...)`:** broke as soon as `pyprover` was imported as a package rather than having its directory manually added to `sys.path`.
- **`src/pyprover/__init__.py` tried `from .async_verifier import async_verifier`:** no such module-level instance was ever defined, only the `AsyncVerifier` class. Now instantiates `async_verifier = AsyncVerifier()` and `ffi_verifier = FFIVerifier()` at package level.
- **`PyProverBridge.verify()` (`src/common/pyprover_bridge.py`) always returned a fabricated `_create_placeholder_result()`** regardless of whether PyProver was installed or what the input code was - it never called into the real verifier at all. Now calls the bundled `src/pyprover` package's `verify_contract()` (via a new `_adapt_local_result()` shape converter) and returns honest results, including an honest "Z3 solver not available" failure when `z3-solver` isn't installed, instead of a fake static result.
- **`detect_pyprover_installed()` used a bare `import pyprover`,** which only worked by accident when `src/` happened to be on `sys.path`; now tries the bundled sibling package first (`from .. import pyprover`) and falls back to an externally-installed top-level package.
- **`PyProverBridge.batch_verify()` was a stub that always returned `None`** when enabled. Now actually splits Python source into top-level functions via `ast` and verifies each one.
- **`AsyncVerifier` (515 lines: race condition, deadlock, and concurrent-variable detection) was completely orphaned** - never called from any code path outside its own module. Added `PyProverBridge.verify_async()`, which uses the verifier's source-only detection methods (no contract object construction required) and surfaces findings as `BugPattern`s in a `UnifiedDebugReport`. Covered by 4 new tests in `tests/test_pyprover_integration.py`.
- **`troubleshooting/phases_5.py` `_phase4_verify()` was labeled "verify solution works"** but only checked that Phase 3 produced at least one remediation step; it cannot actually run anything since the methodology operates on a text problem description, not runnable code. Docstring corrected to describe it honestly as a heuristic readiness check.

### Known gap (not fixed, documented)

- `FFIVerifier` (563 lines: FFI type/memory/lifetime safety) remains implemented but unwired - its `verify()` requires a caller-built `FFIContract`, and nothing in the suite currently constructs one from raw source. Unlike `AsyncVerifier`, there's no source-only entry point to delegate to without that synthesis step. Left as a documented limitation in SKILL.md rather than building a contract-inference layer in this pass.

### Test Suite

- Full suite: **148/148 passing** (`python -m pytest tests/ src/ -q`), up from 144 (added 4 tests for real bridge behavior)

## [2.2.0] - 2026-06-30

### Added

- **C/C++-Debug (Phase 4 of the multi-language roadmap):**
  - `src/cpp_debug/diagnostics.py` - compiles C/C++ with `clang -fsyntax-only -Wall -Wextra` and parses warnings/errors
  - `src/cpp_debug/analyzer.py` - drives the Clang Static Analyzer (`clang --analyze`) for path-sensitive bugs (null deref, memory leaks, div-by-zero)
  - `src/cpp_debug/classifier.py` - classifies raw diagnostics/findings into unified `BugPattern` objects, deduped + severity-sorted
  - `src/cpp_debug/phases.py` - `CppDebugger` orchestrating diagnostics + analyzer + a design-review pass (unsafe string APIs, unmatched raw `new`)
  - `src/cpp_debug/setup.py` - `claude_check_and_install()` for the clang/clang++ toolchain, mirroring `rust_debug/setup.py`
  - 19 new tests in `src/cpp_debug/tests/test_cpp_debug_phase4.py`, all passing against a real clang 18 install
  - `master_debugger/orchestrator.py` now routes `language="c"|"cpp"|"c++"` to `CppDebugger` automatically
  - Added `LanguageType.C` and `ComponentType.{RUST_DEBUG,CPP_DEBUG}` to `common/interop.py`

### Fixed (suite-wide cleanup pass - 20 failing tests → 0)

- `src/__init__.py` was missing entirely, breaking every `from ..x import y` relative import across the package
- 4 test directories (`master_debugger/tests`, `pyprover/tests`, `python_debug/tests`, `test_generator/tests`) were missing `__init__.py`, breaking relative imports under pytest
- `master_debugger/__init__.py` exported the legacy v5 orchestrator only; the documented v6/PyProver/Rust-aware `MasterDebugger` in `orchestrator.py` was never wired into the package's static/runtime/design phases - it appended phase labels without running any real analysis. Now delegates to the real `Phase0StaticAnalysis`/`Phase1RuntimeDebug`/`Phase3DesignReview` for Python.
- `orchestrator_v5.py`'s `classify_risk()` had an overly broad CRITICAL keyword bucket (`open(`, `secret`, `validate`, generic `api`) that false-positived plain file reads as CRITICAL; narrowed to genuinely security/network-sensitive keywords and moved `open(` to its own HIGH-risk check
- Added missing `RiskLevel.LOW` to `master_debugger/types.py`
- `PyProverBridge.verify()` was a stub that ignored its input entirely; implemented real `_convert_to_unified_report()` and `_map_language_type()` methods (previously referenced only by tests, never defined) and removed a dead, broken `_create_placeholder_report()` that constructed `UnifiedDebugReport` with nonexistent kwargs
- Extended `LanguageType` enum from 7 to 11 members (added `C`, `CSHARP`, `WASM`, `ASSEMBLY`) to match the suite's documented "12 PyProver languages" claim
- Added missing `summary: str` field to `UnifiedDebugReport` dataclass (referenced by tests, never defined)
- `rust_debug/borrow_checker.py` and `clippy_linter.py` referenced nonexistent enum members `ComponentType.RUNTIME` / `ComponentType.STATIC` and a nonexistent `.line` attribute on `BugPattern` (real field is `.location`); fixed both, added `ComponentType.RUST_DEBUG`
- `rust_debug/phases.py` constructed `UnifiedDebugReport()` with no arguments despite `component`/`language`/`code` being required fields
- `tests/test_rust_debug_phases_2_3.py` constructed `BugPattern(message=..., line=...)` using field names that don't exist on the real dataclass (`description`/`location` do); fixed 4 call sites
- `src/javascript_debug/tests/test_execution_tracing.py` imported from a stale package name (`verification_debugging_suite`) left over from before the project was renamed
- `src/tests/test_integration.py` asserted `risk_level.value == 'CRITICAL'` against an enum whose value convention is lowercase (`'critical'`) everywhere else in the codebase
- `MASTER_DEBUGGER` component label updated from stale `"master-debugger-v5"` to `"master-debugger-v6"`
- SKILL.md was missing version-history entries for v2.0/v2.1 despite the frontmatter version having moved past v1.2; added retroactive entries plus Rust-Debug/Cpp-Debug component docs (the Rust-Debug section was entirely absent from SKILL.md despite being v2.1's headline feature)

### Test Suite

- Full suite: **144/144 passing** (`python -m pytest tests/ src/ -q`), up from 105 passing / 20 failing before this pass

## [1.1.0] - 2026-06-24

### Added

- **Consolidation & Standardization:**
  - Added root `src/conftest.py` with centralized pytest fixtures and marker registration
  - Generated `API.md` (auto-generated API reference from docstrings)
  - Generated `INTEROP.yaml` (operation metadata, schemas, token costs)
  - Generated `openapi.yaml` (OpenAPI 3.0 specification, 12 operations)
  - Generated `MANIFEST.txt` (feature completeness checklist)
  - Added `.gitignore` to exclude bytecode and auto-generated files

### Changed

- **Documentation Consolidation:**
  - README.md reduced from 71 to 20 lines (references SKILL.md instead of duplicating)
  - SKILL.md condensed from 475 to 413 lines (removed verbose workflow examples)
  - Moved detailed examples to reference section with links to docs/
  - All use-case guidance now centralized in SKILL.md "When to Use Each Component"

- **Test Infrastructure:**
  - Simplified `src/python_debug/conftest.py` (removed duplicate marker registration)
  - Marker registration now centralized in root `src/conftest.py`
  - Shared fixtures (execution_timer, code_scenarios, memory_tracker) available to all tests

- **Standardize-Skill Compliance:**
  - SKILL.md now 413 lines (87-line buffer before 500-line limit)
  - Full standardize-skill compliance: code quality ✅, documentation ✅, testing ✅
  - Ready for skill builder tool usage

### Removed

- Deleted old example files:
  - `src/python_debug/EXAMPLES_v12.0_COMPLETE.py` (11.4KB)
  - `src/python_debug/EXAMPLES_v12_2.py` (11.5KB)
- Removed bytecode from distribution (~250KB `__pycache__` directories)

### Sizes

- **SKILL.md:** 475 → 413 lines (62-line reduction, 87-line expansion buffer)
- **README.md:** 71 → 20 lines (51-line reduction)
- **Package:** ~228KB reduction from consolidated examples + bytecode cleanup
- **Total consolidation:** 800+ lines of redundant code eliminated

### Breaking Changes

- **None.** All consolidation changes are backward compatible.
- Python imports unchanged
- API unchanged
- Test suite 100% compatible

### Migration Path

- No user action required
- Existing code using verification-debugging-suite works without changes
- Type consolidation (Phase 2) deferred to v1.2+ (if planned)

---

## [1.0.1] - 2026-06-24

### Fixed
- **CRITICAL: Fixed circular import issue in master_debugger/phases.py**
  - Lines 70, 71, 104, 127: Converted absolute imports to relative imports
  - Enables Phase 1 (RuntimeDebug), Phase 2 (FormalVerification), Phase 3 (DesignReview)
  - Impact: Master-debugger-v5 orchestrator now fully functional

- **CRITICAL: Fixed import errors in python_debug/conftest.py**
  - Lines 19, 111, 268: Converted absolute imports to relative imports
  - Enables pytest collection and test fixture loading
  - Impact: pytest now discovers and runs 80+ tests

### Added
- **Comprehensive Test Suite (80+ tests)**
  - `src/master_debugger/tests/test_orchestration.py` (10+ tests)
  - `src/python_debug/tests/test_execution_tracing.py` (25+ tests)
  - `src/pyprover/tests/test_verification.py` (15+ tests)
  - `src/test_generator/tests/test_generation.py` (20+ tests)
  - `src/tests/test_integration.py` (10+ tests)

- **Test Infrastructure**
  - pytest.ini configuration with custom markers
  - Parametrized edge case testing
  - Contract-based formal verification tests
  - Integration tests for end-to-end workflows

- **Documentation Updates**
  - Updated SKILL.md with test suite section
  - Test running instructions and examples
  - Test coverage matrix by component
  - Test marker reference guide

---

## [1.0.0] - 2026-06-24

### Added
- Master-Debugger-v5: Complete 4-phase orchestrator
  - Phase 0: Static analysis (mypy, pylint, bandit)
  - Phase 1: Runtime debugging (python-debug)
  - Phase 2: Formal verification (pyprover)
  - Phase 3: Design review (troubleshooting)
- PyProver Phase 2: Contract verification with Z3 solver
- Troubleshooting: Full 5-phase methodology implementation
- Root SKILL.md documentation
- Comprehensive API documentation
- Production package metadata

### Changed
- Merged all 7 component skills into unified suite
- Standardized all type hints and error handling
- Updated all documentation to reflect complete implementation

### Fixed
- Master-debugger-v5 was stub (2.5KB) → now full orchestrator
- PyProver was Phase 3 only → now includes Phase 2
- Troubleshooting was minimal stub → now full 5-phase
- Missing root documentation → now comprehensive SKILL.md
- Missing packaging metadata → now setup.py, skill.json

---

## [0.5.0] - 2026-06-22

### Initial
- Suite skeleton with partial components
- python-debug, code-orchestrator, test-generator functional
- master-debugger-v5, pyprover, troubleshooting stubs only
