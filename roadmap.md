# Debug-Suite Roadmap

**Current version:** 2.2.5
**This document supersedes:** the original `debug-suite-v2_1` Phase 1-3 roadmap (reproduced in §9 below, updated with current status)
**Compiled:** June 30, 2026, from a full conversation-history search across every component skill that was merged into this suite (pyprover, python-debug, master-debugger, test-generator, code-orchestrator, troubleshooting, standardize-skill)

---

## 0. How to read this document

Every component in this suite was developed independently across many sessions before being merged into a single package. This search found that the merge was **lossy and, in pyprover's case, inconsistent with its own version history** (see §1). This document exists to make that loss visible and actionable rather than re-hidden behind a clean-looking CHANGELOG.

**A `legacy_code/` folder ships alongside this document** (same directory level, i.e. `legacy_code/` not `src/legacy_code/`) containing actual recovered code fragments for several of the items below - not complete, not tested, often missing the middle of a function where a search snippet was truncated, but real code rather than a re-description of it. Each fragment is marked with exactly what's missing and which conversation-search query would likely recover more. Start there before re-deriving anything from scratch; see `legacy_code/README.md` for the index.

Each feature entry below has a status tag:

- **MISSING** - never made it into the bundled `src/`, confirmed absent by direct file inspection
- **PARTIAL** - present but reduced in scope compared to the source chat
- **PRESENT** - confirmed present and working in v2.2.2 (listed for completeness/contrast, not action)
- **UNCLEAR** - a past audit claimed this was complete, but hands-on testing this session contradicts that claim (see §1)

---

## 1. Critical finding: PyProver has at least three divergent lineages, and the merged one is the most feature-poor

Conversation history shows **three separate PyProver development branches** that were never reconciled with each other:

| Branch | Versions | Core focus | Source chats |
|---|---|---|---|
| **A: Library-integration branch** | v6.1 → v6.2 → v6.3 → v7.0 | SymPy/Hypothesis/beartype, then Pydantic/dataclasses, then Coq/Lean/SMT-LIB proof export | [v6.1 library analysis](https://claude.ai/chat/881eb4f3-14e4-4ac9-b0ec-747ff30c0c93), [v6.2 implementation](https://claude.ai/chat/f0d6606b-9d4a-4273-9c4f-1be96fc3ba95), [v7.0 unification](https://claude.ai/chat/ea78b485-ea9c-438a-9184-8ba7e63f67ed) |
| **B: Multi-language adapter branch** | v8.1 → v8.2 → ... → v10.2 → v11.1 → v11.2 | Algorithm templates (binary search, recursion, state machines), 9-12 language adapters, language-adapter meta-system, 4/5-layer tool-orchestration stack, CBMC/KLEE | [v8.1/8.2 chromium test](https://claude.ai/chat/02da3b25-a7a5-4969-ba32-4d2e7d0db51c), [v10.2-v11.1 Rust/C++/meta-adapter](https://claude.ai/chat/d0b4e00c-15af-4cf8-bdf7-219dee000dc2), [v11.2 audit + v12.0 design](https://claude.ai/chat/76ba9db8-7c5a-4757-990f-a2f78decd6ff), [v13.1 chromium 5-layer test](https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26) |
| **C: The branch actually merged into this suite** | "v14.0" | Reduced contract verifier (comment-text scanning), async/FFI/token-profiler Phase 3 additions | [standardization/compliance audit](https://claude.ai/chat/52160be0-aec1-4647-ac65-8ccd23ec161c), [code upgrade to v13 session](https://claude.ai/chat/f076b379-5374-45c4-a796-67498d72f844) |

**The version number is not a reliable indicator of feature parity across these branches.** Branch C's `contract_verifier.py` (109 lines, the file actually in `src/pyprover/` today) implements none of what Branch B's v13.1 had at the same nominal version distance: no loop invariant verification, no parallel/batch verification, no contract simplification, no per-language AST adapters, no SHA256 caching, no CBMC/KLEE integration. It is closer in capability to Branch C's own much earlier ancestor than to anything in Branch B.

**A past "completeness audit" chat is itself unreliable and should not be trusted without re-verification.** The [Verification debugger suite completeness review](https://claude.ai/chat/57af6457-e04f-4d52-ba99-1bca2aebf565) chat claims, in a table, that the merged suite has "Loop invariants (Hoare logic) ✅ Complete," "Property testing (Hypothesis) ✅ Complete," and "12-language support ✅ Complete." **None of these are true of the code actually in `src/pyprover/` as of v2.2.2** - confirmed by direct inspection and execution this session (no `loop_verifier.py`, and `ContractVerifier` does the identical text scan regardless of declared language). The Hypothesis claim is sharper still: `requirements.txt` lists `hypothesis>=6.0` as a dependency, but `grep -rl "import hypothesis" src/` returns **zero files** - it's a phantom dependency, declared and never imported anywhere in the entire suite, not just absent from pyprover specifically. That audit appears to have compared file *counts* and SKILL.md *claims* rather than running the code, which is exactly the failure mode this suite's CHANGELOG 2.2.0-2.2.2 entries have been fixing elsewhere (stubs and placeholders that "look" complete). Treat any future claim of "100% feature parity" with the same skepticism until it's been exercised end-to-end with real input, the way the 2.2.1/2.2.2 fixes were verified.

---

## 2. PyProver: features to restore

All items below are **MISSING** from `src/pyprover/` in v2.2.2 unless noted otherwise. Effort estimates are taken directly from the original roadmap chats, not re-derived.

### 2.1 Core verification engine (Branch B, v13.0/v13.1)

| Feature | What it does | Est. size | Source | Recovered fragment |
|---|---|---|---|---|
| `loop_verifier.py` | INIT/STEP/TERM loop invariant verification (Hoare-logic style) | ~part of v13.0 patch set | [Code upgrade to v13](https://claude.ai/chat/f076b379-5374-45c4-a796-67498d72f844) | `legacy_code/pyprover_v13_loop_verifier.py`, `legacy_code/pyprover_loop_invariant_v2_prototype.py` |
| `parallel_verifier.py` | ThreadPoolExecutor-based batch verification across many functions at once | ~part of v13.0 patch set | same | none recovered - module docstring only, see §2.5/legacy_code note |
| SHA256 result caching | Skip re-verifying unchanged code | ~part of v13.0 patch set | same | none recovered |
| `ContractSimplifier` | Iterative Z3-implication-check removal of redundant `@requires`/`@ensures` clauses; `ContractSimplificationResult` with `.summary()`/`.as_decorators()` | v13.1 | same | `legacy_code/pyprover_v13_contract_simplifier.py` |
| Generator expression support | `all()`/`any()` inside contracts | v13.0 | same | none recovered |
| Conditional postconditions | `if cond: ensure` → Z3 `Implies` | v13.0 | same | none recovered |
| BINARY_SEARCH / RECURSION / STATE_MACHINE templates | Automatic invariant generation for these three algorithm shapes; structural induction for recursion | v8.2 | [v8.1/8.2 chromium test](https://claude.ai/chat/02da3b25-a7a5-4969-ba32-4d2e7d0db51c) |
| `while_loops=True` on `@unroll_loops`, `@state_tracking`, `@assume` decorators | Real-world loop/mutation/external-constraint support | v8.2 | same |
| Equivalence checking | Prove two implementations equivalent | proposed, not built | [Code upgrade to v13](https://claude.ai/chat/f076b379-5374-45c4-a796-67498d72f844) |
| Proof artifact extraction (Phase 3D) | Export the actual Z3 proof object/certificate | ~300 LOC, 25+ tests, planned for v15.0 | [Pyprover optimization recommendations](https://claude.ai/chat/60e17a77-0ab6-4070-b7b4-0134181ef034) |
| Contract inference (Phase 4) | Weakest-precondition / strongest-postcondition / loop-invariant inference - generate contracts instead of requiring them | ~400 LOC, 30+ tests, planned for v15.0 | same |

### 2.2 Multi-language support

**PRESENT but reduced:** the bundled bridge (`pyprover_bridge.py`) maps 11 `LanguageType` values and the local `ContractVerifier` will accept any of them, but it runs the *identical* comment-text scan for every language - there is no actual per-language parsing.

**MISSING:**

| Feature | What it does | Source | Recovered fragment |
|---|---|---|---|
| Per-language adapter system (9-12 languages: Python, JS, TS, Rust, C Safe Subset, C++20, Go, Java, C#, WASM, NASM, FASM) | Real AST-level parsing and contract extraction per language, not text scanning | [v10.2-v11.1 Rust/C++/meta-adapter](https://claude.ai/chat/d0b4e00c-15af-4cf8-bdf7-219dee000dc2) | `legacy_code/LANGUAGE_ADAPTER_GUIDE_recovered.md` (interface only, no per-language implementations) |
| `LANGUAGE_ADAPTER_GUIDE.md` | Universal template letting a future Claude instance build a new language adapter in ~15 minutes | same | `legacy_code/LANGUAGE_ADAPTER_GUIDE_recovered.md` |
| `TOOL_ORCHESTRATION_GUIDE.md` | Registry of complementary tools per language + automatic invocation across all 4-5 verification layers | same | none recovered |
| Node.js subprocess JS parsing | The original Python `esprima` parser was 10x slower (39ms vs 3-4ms) than shelling out to Node + `acorn`; fix was designed but its target file doesn't exist in the bundled code | [Testing pyprover on chromium](https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26) | `legacy_code/pyprover_js_nodejs_parser_fix.py` |
| Go adapter package-scope function detection | Known regex bug: package-level (non-method) Go functions weren't matched | same | `legacy_code/verification_stack_and_bugs.md` (bug description only, no fix code recovered) |
| Multiline contract extraction | `@requires(\n "a and "\n "b"\n)` across multiple lines wasn't parsed; single-line-only regex bug | same | `legacy_code/pyprover_multiline_contract_regex_fix.py` |

### 2.3 The 5-layer verification stack (Branch B)

A documented architecture that doesn't exist in the merged suite at all:

```
Layer 5: FORMAL VERIFICATION      Z3, cvc5 fallback, loop invariants
Layer 4: PROPERTY TESTING         Hypothesis (Python), Node.js (JS), cargo test (Rust)
Layer 3: BOUNDED MODEL CHECKING   CBMC, KLEE (C/C++ exhaustive path analysis)
Layer 2: RUNTIME DETECTION        ASan, UBSan, compiled assertions
Layer 1: STATIC ANALYSIS          mypy, pylint, GCC, Clang, rustc
```
Source: [Testing pyprover on chromium codebase](https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26) - this chat actually installed CBMC v5.95.1 and ran the full stack against 4 real Chromium-style functions (100% verified). **CBMC/KLEE integration is a natural fit for `cpp_debug` (Phase 4, already done) as a Phase 6 addition** rather than living in pyprover - see §9 Phase 6.

Full stack diagram, confirmed-working tool inventory, and the 5 known bugs + 4 proposed-but-unbuilt features from this session are recovered in full in `legacy_code/verification_stack_and_bugs.md`.

### 2.4 Library integrations (Branch A, v6.2-v7.0)

| Feature | What it does | Source |
|---|---|---|
| SymPy expression simplification | 10-100x faster Z3 verification by simplifying contracts before solving | [v6.1 library analysis](https://claude.ai/chat/881eb4f3-14e4-4ac9-b0ec-747ff30c0c93), [v6.2 implementation](https://claude.ai/chat/f0d6606b-9d4a-4273-9c4f-1be96fc3ba95) |
| Hypothesis property-based testing (built into pyprover itself, not just test-generator) | 1000+ random test cases combined with formal proof | same |
| beartype runtime type checking | Zero-boilerplate runtime type safety wrapper | same |
| Pydantic input validation | Boundary validation layer | [v7.0 unification](https://claude.ai/chat/ea78b485-ea9c-438a-9184-8ba7e63f67ed) |
| dataclass contract organization | Cleaner internal contract storage | same |
| Coq proof export | Export formal proofs to Coq | same |
| Lean 4 proof export | Export formal proofs to Lean 4 | same |
| SMT-LIB interoperability | Export raw SMT-LIB for other solvers | same |

**Note:** §2.1's `ContractInputTooLargeError` size guard (added in v2.2.2) is a reasonable adaptation of Branch B's security-hardening work, but Branch B's actual hardening target was a real expression parser with nesting-depth limits - that parser doesn't exist in Branch C, so the original fix doesn't directly port. See [Pyprover compliance roadmap](https://claude.ai/chat/52160be0-aec1-4647-ac65-8ccd23ec181c) for the full security audit (4 vulnerabilities found via red-team testing: DoS via nesting depth, newline injection, and two more not yet identified in this search - re-read that chat in full before restoring this section).

### 2.5 Smart features identified but never built (any branch)

From the Chromium red-team session, proposed but not implemented anywhere:

- Automated contract strengthening from counterexamples
- Counterexample-driven test generation (this *did* get built, but inside `test_generator`, not pyprover - see §4)
- Interactive contract debugger

Source: [Testing pyprover on chromium codebase](https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26)

### 2.6 Standardize-skill compliance debt

The [Pyprover compliance and token-efficient debugging roadmap](https://claude.ai/chat/52160be0-aec1-4647-ac65-8ccd23ec161c) chat scored Branch B's v13.1 at **15% standardize-skill compliance**: missing type hints, no `INTEROP.yaml`, no structured error handling, six oversized modules, no packaging files, plus the 4 security vulnerabilities from §2.4. Branch C (the merged code) has `INTEROP.yaml`/`API.md`/`openapi.yaml` at the suite level already (added in the 1.1.0 consolidation), but the security-hardening and type-hint work from this audit was never specifically re-verified against Branch C's actual `contract_verifier.py`/`async_verifier.py`/`ffi_verifier.py`. Re-run this audit against the current files before considering pyprover "compliant."

---

## 3. Python-debug: gaps

**PRESENT and confirmed working:** all 8 advanced v12.x APIs (`get_true_aliases`, `get_async_events`, `get_generator_events`, `get_call_stack_at`, `get_variable_mutations`, `get_object_references`, `get_performance_metrics`, `get_execution_summary`), true `gc`-based object-ID aliasing, `TrackedGenerator`/`TrackedAsyncContext` wrappers, `conftest.py`, `benchmark_debug.py`, `analyze_timeline.py`. Sources: [v11.1→v12.0 upgrade](https://claude.ai/chat/143347d4-1590-4ce3-ada6-0dd50c6cce80), [v12.0.1→v12.2.0 completion](https://claude.ai/chat/6fa9dcbf-8b2b-4ba9-9037-d61974dad6e7), [v12.3.0 ENHANCED repackaging](https://claude.ai/chat/87025f90-5c10-45b3-8fc8-eea6d2563663).

**MISSING (minor, dev-tooling only):** the "ENHANCED" v12.3.0 package added complementary dependencies that never made it into the suite's `requirements.txt`: `pytest-timeout`, `pytest-benchmark`, `ruff`, `black`, `memory-profiler`, `psutil`, `pdoc`, `click`, `tabulate`, `colorama`. A 14-target `Makefile` (`make perf`, `make benchmark-custom`, etc.) was also built and not carried forward. Low priority - these are developer-experience tools, not functional gaps. Source: [Pydebug skill testing and repackaging](https://claude.ai/chat/87025f90-5c10-45b3-8fc8-eea6d2563663).

---

## 4. Test-generator: status

**PRESENT and confirmed working:** metamorphic testing, mutation testing, red-team/adversarial tests (`generate_red_team_tests`, `generate_fuzzing_payloads` - DoS, injection, type confusion, unicode bypass, boundary overflow, state corruption), fuzzing payload generation. Confirmed by direct inspection of `src/test_generator/test_generator.py` this session.

**Architectural note, not yet acted on:** a [past planning session](https://claude.ai/chat/973a49ee-f592-4c14-83fb-7e97f028d5c7) explicitly scoped test-generator's relationship to pyprover ("test-generator does concrete/metamorphic/mutation testing; pyprover does formal proof + property testing; zero overlap") and recorded a memory instruction: *"Eventually integrate as a call to master-debugger-v5 (bugs found → tests generated → verify fix). Currently standalone; future roadmap includes v2.0 orchestration layer."* This integration has not been built - `master_debugger/orchestrator.py` does not call into `test_generator` anywhere today. This is a contained, well-scoped integration task: when `debug_comprehensive()` finds an issue, automatically call `test_generator` to produce a regression test for it.

---

## 5. Master-debugger: architectural feature to consider restoring

**Already resolved by the current code-based orchestrator (v6):** the historical "nested skills described but never invoked" bug ([root-cause chat](https://claude.ai/chat/8974967f-3f2d-46ab-aea4-47940059a278), [fix chat](https://claude.ai/chat/547632e3-6f74-48a4-b20c-d3f74f2eba46)) doesn't apply to `src/master_debugger/orchestrator.py` - it's real Python code that actually calls `Phase0StaticAnalysis.run()`, `Phase1RuntimeDebug.run()`, etc., not LLM-instruction-based skill invocation. No action needed here.

**MISSING - conceptual model, not code:** [master-debugger v3.0](https://claude.ai/chat/222c9b8e-ecf8-41ec-97f1-dfc169c5f946) was rewritten around an explicit **three-stream blind-spot model**: python-debug, pyprover, and troubleshooting each get a documented "blind spot" section (what that tool structurally cannot see), the three run as parallel complementary investigations rather than redundant verification passes, and there's an explicit synthesis/conflict-resolution phase at the end. The current `orchestrator.py` runs phases sequentially without documenting what each phase *can't* catch, and has no conflict-resolution step when, e.g., a static check and a runtime trace disagree. Worth restoring as documentation + a `_synthesize_with_blind_spots()` step, low effort.

---

## 6. Code-orchestrator: status

**PRESENT and confirmed complete** per a contemporaneous audit: multi-function analysis, GitHub project cloning/analysis, file structure decomposition, topological sort/leaf-first ordering, coverage tracking, tool recommendation engine, state machine coordination, checkpoint/handoff system, multi-file orchestration, type stub generation, project structure mapping. Source: [Verification debugger suite completeness review](https://claude.ai/chat/57af6457-e04f-4d52-ba99-1bca2aebf565) (caveat from §1 applies generally to this chat's claims, but code-orchestrator's feature list matches what's actually in `src/code_orchestrator/` - 15 files, matching names - so this one specific table is corroborated by file inspection, unlike the pyprover table in the same chat).

No restoration work identified for this component.

---

## 7. Environment capabilities confirmed available (for future phases)

From a sandbox capability-discovery session, confirmed installable/available in this environment:

- Language runtimes via `apt`: `go`, `javac`, `rustc`, `cargo`, `dotnet`, `wabt` (WASM), `mono-mcs`, `nasm`, `fasm`
- `go-staticcheck` via apt (not the blocked `proxy.golang.org`)
- GitHub: public repo cloning and raw file downloads work; `api.github.com` requires a `GH_TOKEN`
- `cvc5` - SMT solver, usable as a Z3 fallback
- `AFL++` - coverage-guided fuzzing
- `semgrep` - cross-language static analysis
- `mutmut` - Python mutation testing (alternative/complement to test-generator's built-in mutation testing)
- `biome` - fast JS/TS linter
- `cbmc` - confirmed installable and working (v5.95.1), used for real in the chromium 5-layer test

Source: [Code review and bug checking process](https://claude.ai/chat/76ba9db8-7c5a-4757-990f-a2f78decd6ff), [Testing pyprover on chromium codebase](https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26)

This directly de-risks §9 Phase 6 (KLEE/CBMC) below - CBMC at minimum is known-installable in this exact environment, not just in theory.

---

## 8. Suggested priority order

Given the size of §2-§5, a reasonable next-session order (highest restoration value per unit effort first):

1. **Master-debugger ↔ test-generator integration** (§4) - small, well-scoped, closes a recorded memory instruction
2. **Loop invariant verification + contract simplification** (§2.1) - the two highest-value pieces of the v13.1 core engine, self-contained, don't require multi-language adapter work
3. **Re-run the standardize-skill security audit** (§2.6) against the actual current `pyprover/` files - cheap, and 2 of the 4 known vulnerabilities are still unconfirmed-fixed
4. **CBMC integration into `cpp_debug`** (§2.3, §7) - de-risked by confirmed environment support, natural extension of the already-complete Phase 4
5. **Per-language adapters** (§2.2) - largest effort, highest payoff for the "12-language" claim the suite's own SKILL.md still makes
6. **Library integrations** (§2.4) and **proof export** (§2.1 Phase 3D/4) - lowest priority; valuable but furthest from what master-debugger's orchestration actually exercises today

---

## 9. Original Phase 4-10 roadmap (C/C++/Assembly), with current status

Reproduced from the uploaded `debug-suite-v2_1` roadmap document, updated against v2.2.2.

### Phase 4: C/C++ AST Parser (Clang) - ✅ DONE (v2.2.0)
Originally estimated 800-1000 lines / 2-3 weeks. Shipped in v2.2.0 as `src/cpp_debug/` (diagnostics.py, analyzer.py, classifier.py, phases.py, setup.py), 19 passing tests against a real clang 18 install. Uses `clang -fsyntax-only`/Clang Static Analyzer rather than raw libtooling AST bindings - narrower than originally scoped (no template instantiation graph, no implicit-cast extraction) but functional and tested.

### Phase 5: C/C++ DWARF Symbols - ❌ NOT DONE
Est. 600-800 lines / 2 weeks. Read DWARF debug info, analyze memory layout, detect use-after-free/double-free via `pyelftools`. No change since original roadmap.

### Phase 6: C/C++ KLEE Symbolic Execution - ❌ NOT DONE
Est. 500-700 lines / 2-3 weeks. **Now also see §2.3/§7 above** - this should absorb the CBMC integration too, since both were demonstrated working together in the chromium 5-layer test and the original Phase 6 scope (KLEE-only) artificially separated two tools that are normally used together at the same layer.

### Phase 7: C-Debug (simpler C variant) - ❌ NOT DONE
Est. 300-400 lines / 1-2 weeks. Reuse `cpp_debug` components, add `strace` syscall tracing.

### Phase 8: Assembly Disassembly & CFG - ❌ NOT DONE
Est. 1000-1200 lines / 2-3 weeks. Capstone disassembly, control flow graph construction.

### Phase 9: Assembly Dataflow & Taint Analysis - ❌ NOT DONE
Est. 1000 lines / 2 weeks.

### Phase 10: Assembly angr Symbolic Execution - ❌ NOT DONE
Est. 600-800 lines / 2-3 weeks.

**Remaining estimated effort for Phases 5-10:** ~7,000-7,200 lines, 16-21 weeks (slightly reduced from the original ~8,000/18-24 weeks since Phase 4 is complete).

---

## 10. Source chat index

All chats referenced above, for quick navigation:

- https://claude.ai/chat/881eb4f3-14e4-4ac9-b0ec-747ff30c0c93 - PyProver v6.1 library analysis (Hypothesis/SymPy/beartype recommendation)
- https://claude.ai/chat/f0d6606b-9d4a-4273-9c4f-1be96fc3ba95 - PyProver v6.2 implementation
- https://claude.ai/chat/ea78b485-ea9c-438a-9184-8ba7e63f67ed - PyProver v7.0 unification (Coq/Lean/SMT-LIB)
- https://claude.ai/chat/02da3b25-a7a5-4969-ba32-4d2e7d0db51c - PyProver v8.1/8.2 chromium test + algorithm templates
- https://claude.ai/chat/d0b4e00c-15af-4cf8-bdf7-219dee000dc2 - PyProver v10.2-v11.1 Rust/C++20/meta-adapter system
- https://claude.ai/chat/76ba9db8-7c5a-4757-990f-a2f78decd6ff - PyProver v11.2 audit, v12.0 design, environment capability discovery
- https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26 - PyProver v13.1 chromium 5-layer test, bug list, CBMC install
- https://claude.ai/chat/f076b379-5374-45c4-a796-67498d72f844 - PyProver v13.0/v13.1 code upgrade (loop/parallel/simplifier)
- https://claude.ai/chat/52160be0-aec1-4647-ac65-8ccd23ec161c - PyProver standardize-skill compliance audit (15% score, security vulns)
- https://claude.ai/chat/57af6457-e04f-4d52-ba99-1bca2aebf565 - Verification-debugging-suite completeness review (see §1 caveat)
- https://claude.ai/chat/7489606e-c7df-448b-8cf6-c72250828948 - Earlier suite completeness review + fixes (TestGenerator class, FunctionResult import, z3 import placement)
- https://claude.ai/chat/143347d4-1590-4ce3-ada6-0dd50c6cce80 - python-debug v11.1→v12.0 (true aliasing, async, generators, call stack, mutations)
- https://claude.ai/chat/6fa9dcbf-8b2b-4ba9-9037-d61974dad6e7 - python-debug v12.0.1→v12.2.0 completion
- https://claude.ai/chat/87025f90-5c10-45b3-8fc8-eea6d2563663 - python-debug v12.3.0 ENHANCED repackaging (extra tooling)
- https://claude.ai/chat/973a49ee-f592-4c14-83fb-7e97f028d5c7 - test-generator red-team testing + master-debugger integration plan
- https://claude.ai/chat/f071a235-41a8-4688-aacb-320f48a04c09 - code-orchestrator v1.1 GitHub integration implementation
- https://claude.ai/chat/60e17a77-0ab6-4070-b7b4-0134181ef034 - PyProver v15.0 expansion handoff (proof artifacts, contract inference) + code-orchestrator handoff
- https://claude.ai/chat/222c9b8e-ecf8-41ec-97f1-dfc169c5f946 - master-debugger v3.0 three-stream blind-spot rewrite
- https://claude.ai/chat/8974967f-3f2d-46ab-aea4-47940059a278 - master-debugger v5.0 nested-skill bug discovery (Forge Neo testing)
- https://claude.ai/chat/547632e3-6f74-48a4-b20c-d3f74f2eba46 - master-debugger v5.0 nested-skill invocation fix
- https://claude.ai/chat/bfb680e7-c8c1-4001-aa78-1635c428a33b - standardize-skill original build + self-validation
- https://claude.ai/chat/7f6e4283-b92a-496f-a744-b27f6aea629a - suite consolidation + javascript-debug merge (v1.1.0→v1.2.0)
- https://claude.ai/chat/fd6f5b89-b113-4f21-9e82-2c0190bb5339 - debug-suite v2.1 Rust-debug Phases 1-3 (source of the uploaded original roadmap document)
- https://claude.ai/chat/0d6f7cd2-6bba-4cdd-9fc5-0def656850e8 - v2.2.0 cleanup session (packaging bugs, Phase 4 cpp_debug)
