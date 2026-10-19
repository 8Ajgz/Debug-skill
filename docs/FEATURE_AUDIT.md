# Feature audit: old features versus the current code

Every feature named in the archive's roadmap (`roadmap.md`), component SKILL.md files and CHANGELOG was checked against the repository. Status meanings:

- **Incorporated**: present in the code, with a test or a direct check
- **Partial**: some of the feature is present
- **Superseded**: replaced by a different design, which is named
- **Not incorporated**: absent from the code, and no decision recorded yet
- **Never built**: planned in the roadmap, never implemented in any archived version
- **Unverifiable**: described only in source chats, which are not in the archive

## PyProver (roadmap section 2)

| Feature | Status | Where / why |
|---|---|---|
| Loop invariant verification, INIT and PRESERVATION | Incorporated | `pyprover/loop_verifier.py`. Annotations are `# Invariant:` comments, not the v13 `@loop_invariant` decorator (see below) |
| Parallel batch verification | Incorporated | `pyprover/parallel_verifier.py`, worker processes |
| SHA256 result caching | Incorporated | `pyprover/verification_cache.py` |
| Contract simplification | Incorporated | `pyprover/contract_simplifier.py` |
| `all()` / `any()` generator expressions in contracts | Incorporated | `pyprover/quantifiers.py`, `tests/test_quantifiers.py` |
| Conditional postconditions, `if cond: ensure` | Incorporated | `contract_verifier.py` (`_conditional_parts`); v6 regex version replaced |
| Invariant templates: binary search, min/max, accumulator, filter, scan, state machine | Incorporated | `pyprover/invariant_templates.py`. Checked at runtime against reference loops; not proved |
| Invariant template: recursion | Not incorporated, on purpose | Its `(base) OR (step)` form is not a valid invariant |
| Invariant template: while loop | Not incorporated, on purpose | Its bound is a fixed guess, not an invariant |
| `@unroll_loops`, `@state_tracking`, `@assume` | Not incorporated, on purpose | In v8.2 they only set function attributes; nothing reads them |
| Equivalence checking | Incorporated | `pyprover/equivalence_verifier.py` |
| Proof artifact extraction (Phase 3D) | Never built | Planned for v15.0 in the roadmap |
| Contract inference (Phase 4) | Never built | Planned for v15.0 in the roadmap |
| Per-language adapters, 9 to 12 languages | Partial | Python uses `ast`; JavaScript, Rust, C, C++ and assembly have their own debug modules. Go, Java, C#, TypeScript and WebAssembly have no parser. The v11 adapters are in `legacy_code/`, not wired in |
| Adapter guide and tool orchestration guide | Not incorporated | Documentation only, and no recovered text beyond `legacy_code/` |
| Node.js acorn parsing for JavaScript | Superseded | `javascript_debug` runs Node directly; contract clauses are text, so no parser is needed |
| Go package-scope regex fix | Not applicable | No Go adapter (see above) |
| Multiline contract extraction | Superseded | Each `# Pre:` / `# Post:` line is read separately; the decorator form does not exist here |
| ContractInputTooLargeError size guard | Incorporated | `contract_verifier.py` limits |
| Five-layer stack, layer 1 static analysis | Incorporated | `master_debugger` phase 0: mypy, pylint, bandit, semgrep |
| Five-layer stack, layer 2 runtime sanitizers (ASan, UBSan) | Not incorporated | Valgrind is in `c_debug`; ASan and UBSan are not |
| Five-layer stack, layer 3 bounded model checking | Incorporated | CBMC and KLEE wrappers in `cpp_debug/symbolic_executor.py` |
| Five-layer stack, layer 4 property testing | Partial | Python only (`property_tester.py`). JavaScript and Rust property testing are missing |
| Five-layer stack, layer 5 formal verification (Z3) | Incorporated | `contract_verifier.py` and the modules around it |
| Hypothesis property testing | Incorporated | `pyprover/property_tester.py`, optional dependency |
| SymPy simplification, beartype, Pydantic | Not incorporated | Library choices from v6/v7, not features. Not reviewed for value |
| Coq and Lean 4 export | Never built | The v7.0 code was a stub with no translation |
| SMT-LIB export | Incorporated | `pyprover/smtlib_export.py`, re-solved in tests |
| Counterexample-driven contract strengthening | Never built | Proposed in the Chromium session only |
| Interactive contract debugger | Never built | Proposed in the Chromium session only |
| Float precision (FloatWorkAround) | Superseded | Floats are Z3 Real (`contract_verifier.seed_real_env`) |
| Strings, `len`, `abs`, `min`, `max` | Incorporated | `pyprover/z3_builtins.py` |
| Ghost state, owner tracking | Incorporated | `pyprover/ghost_state.py` |
| Loop verifier with quantifiers (roadmap 18.2) | Not incorporated | Deferred in the roadmap; still open |
| Standardize-skill security audit (roadmap 2.6) | Not verified | Not re-run in this audit |

## Python debug (roadmap section 3)

| Feature | Status | Where / why |
|---|---|---|
| Eight advanced APIs (`get_true_aliases`, `get_async_events`, `get_generator_events`, `get_call_stack_at`, `get_variable_mutations`, `get_object_references`, `get_performance_metrics`, `get_execution_summary`) | Incorporated | `python_debug/debug_report.py` |
| Object-identity aliasing | Incorporated | `debug_report.py`, using `gc` |
| `TrackedGenerator`, `TrackedAsyncContext` | Incorporated | `debug_report.py`, `benchmark_debug.py` |
| `conftest.py`, `benchmark_debug.py`, `analyze_timeline.py` | Incorporated | Present |
| FIXED build: last-line assignments (final state, aliases, mutations) | Incorporated | `debug_report.py`. Fixed this audit: mutations for a variable first assigned on the last line were dropped, and `get_variable_mutations` crashed on events without a snapshot. Tests in `tests/test_last_line_assignment.py` |
| FIXED build: exception info as a dict | Incorporated | `debug_report.py` |
| ENHANCED dev dependencies (pytest-timeout, ruff, black, psutil, ...) and the 14-target Makefile | Not incorporated | Low priority; developer tooling, not runtime features |
| v12.2 example scripts (eight examples) | Not incorporated | The current `examples.py` is a different set of demos |

## Test generator (roadmap section 4)

| Feature | Status | Where / why |
|---|---|---|
| Metamorphic testing | Incorporated | `test_generator/test_generator.py` |
| Mutation testing | Incorporated | `test_generator/test_generator.py` |
| Red-team and fuzzing payloads | Incorporated | `generate_red_team_tests`, `generate_fuzzing_payloads` |
| Real `run_tests` and `measure_coverage` | Incorporated | Fixed in 2.9.5 (formerly hardcoded) |
| Counterexample-driven test generation | Not incorporated | Roadmap says it was built in test_generator; no such code exists |
| Master debugger calls test generator (bugs found, then tests generated) | Partial | `master_debugger/orchestrator.py` phase 5 generates regression tests. The "verify the fix" step is missing |

## Master debugger (roadmap section 5)

| Feature | Status | Where / why |
|---|---|---|
| Code-based orchestrator (no LLM-instruction dispatch) | Incorporated | `master_debugger/orchestrator.py` |
| Synthesis and conflict resolution across streams | Incorporated | 2.9.4, `tests/test_synthesis_conflict_resolution.py` |
| Per-tool blind-spot documentation (v3.0 model) | Partial | Mentioned in comments only. No per-tool section |
| Master-debugger v4 features (13-point risk checklist, phase 0 commands, workflow templates, anti-pattern guardrails) | Unverifiable | Source chats only; no file in the archive |

## Code orchestrator (roadmap section 6)

| Feature | Status | Where / why |
|---|---|---|
| Multi-function and multi-file analysis, GitHub clone and analysis | Incorporated | `multi_file_analyzer.py`, `github_analyzer.py` |
| Decomposition with topological ordering | Incorporated | `decomposition.py` |
| Coverage tracking, tool recommendation, state machine | Incorporated | `coverage.py`, `tool_recommender.py`, `state_machine.py` |
| Checkpoint and handoff | Incorporated | `handoff.py` |
| Type stub generation, project structure mapping | Incorporated | `type_stubs.py`, `project_structure.py` |

## Phases 4 to 10 (roadmap section 9)

| Feature | Status | Where / why |
|---|---|---|
| C/C++ compiler diagnostics and clang analyzer (phase 4) | Incorporated | `cpp_debug` |
| DWARF analysis (phase 5) | Incorporated | `cpp_debug/dwarf_analyzer.py` |
| CBMC and KLEE (phase 6) | Incorporated | `cpp_debug/symbolic_executor.py` |
| C-debug with strace and valgrind (phase 7) | Incorporated | `c_debug/debugger.py` |
| Assembly disassembly, CFG, taint, angr (phases 8 to 10) | Incorporated | `assembly_debug` |
| tree-sitter parsing | Not incorporated, on purpose | Decided against in roadmap 12.2 |

## Other components

| Feature | Status | Where / why |
|---|---|---|
| JavaScript: Promise tracking, aliasing, ten bug patterns | Incorporated | `javascript_debug/`. Ten `BugPatternType` values, the same as the archive |
| py-debug v2.0: line tracking, variable dumps, aliasing, exception context | Incorporated | `python_debug` |
| py-debug v2.0: JSON and human-readable reports, root-cause analysis | Incorporated | `debug_report.py` (JSON), `bug_patterns.py` (root cause) |
| Troubleshooting: domain-aware diagnosis (code, hardware, general) | Incorporated | `troubleshooting/phases_5.py`, fixed in 2.9.5 |
| Standalone troubleshooting skill | Unverifiable | Not in the archive |
| Stubs found in STUBS.md | Incorporated | All fixed in 2.9.5 |

## Open items, in priority order

1. Decorator contract syntax (`@requires`, `@ensures`, `@loop_invariant`), from v11 and v13. The repo uses comments only. This needs a decision on whether the decorator form should be supported.
2. Loop verifier with quantifiers (roadmap 18.2).
3. Master debugger: the "verify the fix" step after regression tests are generated.
4. Per-language contract parsing for Go, Java, C#, TypeScript and WebAssembly.
5. Counterexample-driven test generation, which the roadmap says exists and the code does not have.
6. Runtime sanitizer layer (ASan, UBSan).
7. Property testing for JavaScript and Rust.
8. Developer tooling and the v12.2 example scripts.
9. Standardize-skill security audit re-run.
