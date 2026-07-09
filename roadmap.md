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

### Phase 5: C/C++ DWARF Symbols - ✅ DONE (v2.4.0)
Implemented as `src/cpp_debug/dwarf_analyzer.py` (~340 lines). Reads DWARF via pyelftools, extracts variable layout, classifies stack/global/unknown location kinds, runs three heuristic passes: stack-pointer escape (MEDIUM, conf 0.4), void* untracked heap (MEDIUM, conf 0.45), multi-pointer double-free (HIGH, conf 0.55). Integrated into `CppDebugger.debug()`. 28 tests.

### Phase 6: C/C++ KLEE/CBMC Symbolic Execution - ✅ DONE (v2.4.0)
Implemented as `src/cpp_debug/symbolic_executor.py` (~360 lines). CBMCDriver: `cbmc --unwind 5 --bounds-check --div-by-zero-check --null-pointer-check --overflow-check`. KLEEDriver: `clang -emit-llvm` + `klee --max-time=30s`. SymbolicExecutor runs CBMC then KLEE (C only), deduplicates by (property_type, location). Integrated into `CppDebugger.debug()`. 35 tests (2 skipped — no CBMC in CI).

### Phase 7: C-Debug (simpler C variant) - ✅ DONE (v2.4.0)
Implemented as `src/c_debug/` module (~370 lines). SyscallTracer compiles with `gcc/clang -g -O0` and runs under `strace -f -e trace=%file,%desc,%process,brk,mmap`. _analyse_events() detects: double-close, write/read-after-close (EBADF), ENOMEM on brk/mmap, ENOENT/EACCES on open, fork+exec fd-leak risk. CDebugger combines CppDebugger(dialect="c") + SyscallTracer. MasterDebugger routes `language="c"` to CDebugger. 29 tests.

### Phase 8: Assembly Disassembly & CFG - ✅ DONE (v2.5.0)
`src/assembly_debug/disassembler.py` + `cfg.py` (~430 lines). Capstone disassembly (x86-64/32, ARM, ARM64), raw bytes or ELF .text. CFGBuilder: leader ID, basic block partition, fallthrough/branch/call edges, DFS back-edge detection, BFS reachability. CFGAnalysis: indirect_control_transfer, unreachable_code, back_edge_loop, no_return_path. 26 tests.

### Phase 9: Assembly Dataflow & Taint Analysis - ✅ DONE (v2.5.0)
`src/assembly_debug/dataflow.py` (~280 lines). Forward worklist taint analysis. Seeds: rdi/rsi/rdx/rcx/r8/r9. Transfer: mov/add/sub/xor propagate; call taints rax if any arg tainted. Sinks: tainted→[mem] (HIGH), tainted→indirect branch (CRITICAL), tainted→syscall (HIGH). 33 tests.

### Phase 10: Assembly angr Symbolic Execution - ✅ DONE (v2.5.0)
`src/assembly_debug/symbolic.py` + `phases.py` (~350 lines). CFGFast for function extraction. SimulationManager with LAZY_SOLVES collects unconstrained (CRITICAL) and errored (HIGH) states. AssemblyDebugger facade: debug_bytes/debug_binary/debug_source. MasterDebugger routes "assembly"/"asm"/"x86_64"/"arm" to AssemblyDebugger. 27 tests.

**Original Phase 4-10 roadmap: COMPLETE as of v2.5.0. All 355 tests passing.**

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

---

## 11. Session addendum (2026-07-09): root __init__.py completeness, dependency verification, RustDebugger honesty fix, valgrind + cppcheck integration

This section documents work from a single continuous session, in the order it happened. Every claim below was verified by actually running the code in this sandbox, not inferred from reading it - status tags follow §0's convention (DONE / MISSING / bug found).

### 11.1 `src/__init__.py` was completely empty - DONE

The uploaded v2.5.0 archive shipped `src/assembly_debug/`, `src/c_debug/`, `src/cpp_debug/`, `src/rust_debug/` (all real, non-stub code, confirmed by direct inspection) but the root `src/__init__.py` - the single-import public API surface (`from src.master_debugger... import MasterDebuggerV5`, `__all__`, `__version__`) - was 0 bytes. Rebuilt it from the v1.0.0 file, extended with all v2.5.0 additions: PyProver loop verification/contract simplification, the cross-language `PyProverBridge`, and facades for all four new language debuggers (`CppDebugger`, `CDebugger`, `AssemblyDebugger`, `RustDebugger`) plus their supporting types. Verified by `import src` and checking every name in `__all__` resolves via `hasattr`, not just that the import statement doesn't raise.

While verifying, found and fixed one more pre-existing bug in the process: the old `__init__.py` imported `generate_tests`/`TestCase`/`TestGenerationResult` from `src.test_generator` (the package), but that package's own `__init__.py` only ever re-exported `TestGenerator`. This import has been broken since v1.0.0 and never actually ran. Fixed by importing from the submodule (`src.test_generator.test_generator`) directly, matching the deep-import convention already used everywhere else in the file.

Current state: `src/__init__.py`, 122 lines, 59 exports (v2.6.0, after §11.4-11.5 below), `import src` succeeds cleanly, every `__all__` name resolves.

### 11.2 Dependency installability: git vs. pip vs. apt, verified per-tool

None of the previously-`MISSING`-per-`cbmc_available()`/`angr_available()`/`klee_available()` tools needed a git clone + from-source build. Tested each directly in this sandbox (network allowlist: `pypi.org`, `archive.ubuntu.com`, `security.ubuntu.com`, `github.com`/`release-assets.githubusercontent.com`, no `rustup.rs`/`sh.rustup.rs`):

| Tool | Path that works | Verified how |
|---|---|---|
| `angr` | `pip install angr` (PyPI) | Installed, `import angr` clean, `angr_available()` → `True`. Its `unicorn` dependency initially failed to load (`unicornlib.so`); `pip install --upgrade unicorn` fixed it. |
| `capstone`, `pyelftools` | `pip install capstone pyelftools` (PyPI) | Already covered by requirements; confirmed both import cleanly. |
| `cbmc` | **Either** `apt-get install -y cbmc` (Ubuntu universe repo, v5.95.1) **or** the GitHub release `.deb` (`github.com/diffblue/cbmc/releases`, v6.10.0) | Tried the GitHub-release `.deb` path first (downloaded `ubuntu-24.04-cbmc-6.10.0-Linux.deb`, `apt-get install -y ./cbmc.deb`), then discovered apt has it directly too - simpler, prefer apt. `cbmc --version` and `cbmc_available()` both confirmed working either way. |
| `klee` | **Neither pip, apt, nor a GitHub release asset** - checked `api.github.com/repos/klee/klee/releases`, zero prebuilt binaries on any tag, source-only. Requires a specific patched LLVM + uclibc build, realistically a Docker-image install (`klee/klee`), not sandbox-buildable in reasonable time. | Confirmed via GitHub API, not attempted further - would burn significant budget for a tool this suite already reports as unavailable honestly (`klee_available()` correctly returns `False`, and the existing `symbolic_executor.py` docstring already accurately describes KLEE as a "heavier dependency," so no doc fix was needed there). |
| `rustc`, `cargo` | `apt-get install -y rustc cargo` (Ubuntu main repo, v1.75.0) | Installed, `rustc --version`/`cargo --version` both work. |
| `clippy` | `apt-get install -y rust-clippy` (**not** `clippy` or `cargo-clippy` - the Debian/Ubuntu package name is `rust-clippy`, or `rust-N.NN-clippy` for a version-pinned toolchain match) | Installed, `cargo clippy --version` works. |
| `valgrind` | `apt-get install -y valgrind` (Ubuntu main repo) | Installed, ran against a real 40-byte leak, caught it exactly (`definitely lost: 40 bytes in 1 blocks`, correct allocation site). See §11.4. |
| `cppcheck` | `apt-get install -y cppcheck` (Ubuntu universe repo) | Installed, ran against the same leak with `--enable=all`, caught it independently (`memleak`). See §11.5. |

**Fixed:** `rust_debug/setup.py`'s `SETUP_INSTRUCTIONS`/`CLAUDE_INSTRUCTION`/`REQUIRED_TOOLS` previously led with the `rustup.rs` curl-installer as "Option 1 (Recommended)," which doesn't work in sandboxed Claude environments without that domain allowlisted. Rewrote to lead with apt (verified working here), rustup as an explicit fallback for environments with broader network access, and added a note about the `rust-clippy` package-name gotcha. `cpp_debug/setup.py` and `symbolic_executor.py`'s CBMC/KLEE docstrings were checked and are already accurate (apt-first, KLEE described as heavyweight); no changes needed there.

### 11.3 Real bug found and fixed: `RustDebugger.debug()` reported false confidence when rustc/clippy weren't installed

`BorrowCheckerParser.parse_borrow_checker_output()` and `ClippyLinter.run_clippy()` both correctly detect and record tool availability (`rustc_available`, `clippy_available`) and degrade to empty results when the tool is missing - but `RustDebugger.debug()` in `phases.py` never read either flag. Result: with neither tool installed, it still returned `risk_level=LOW`, `confidence_score=0.95`, summary `"✅ No borrow checker or Clippy violations"` - indistinguishable from a real clean-code result, because no code path ever checked whether an actual check had run. Every other new v2.5.0 module (`dwarf_available`, `cbmc_available`/`klee_available`, `strace_available`, `capstone_available`, `angr_available`) correctly surfaces tool absence to the caller; Rust was the one exception.

**Fixed** in `src/rust_debug/phases.py`, following the same pattern `CppDebugger.debug()` already uses (`confidence_score = 1.0 if diagnostics.get("tool_available") else 0.0`):
- `phases_executed` now lists only the phases that actually ran (`["static"]` alone if neither tool is present, vs. `["static", "borrow_checker", "clippy"]`), instead of the old hardcoded `["static", "runtime"]`.
- `confidence_score`: `0.95` only when both tools ran and found nothing (unchanged from before, now honestly earned); `0.8` when real patterns were found (unchanged); `0.4` when only one tool ran; `0.0` when neither ran.
- `summary` distinguishes four cases explicitly instead of collapsing "no tools ran" into the same string as "tools ran, found nothing": both-available-clean (unchanged text), rustc-only, clippy-only, and neither-available (explicit warning that the result doesn't indicate clean code).

Verified all three states with real tools: installed rustc/cargo/clippy via apt in this sandbox, confirmed `confidence=0.0`+warning with neither installed, `confidence=0.95` clean with both installed and no bug, and `risk=CRITICAL` correctly caught on a real use-after-move borrow violation with both installed.

### 11.4 New: valgrind (memcheck) integration into `c_debug` - DONE

Added `ValgrindRunner`/`ValgrindReport`/`valgrind_available()` to `src/c_debug/debugger.py`, wired into `CDebugger.debug()` alongside the existing `SyscallTracer`, plus a new `CDebugger.valgrind_only()` convenience method mirroring `strace_only()`. This closes a real capability gap: `cpp_debug`/`c_debug` previously had static analysis (Clang, CSA) + DWARF + strace, but nothing that instruments actual memory accesses at runtime - so leaks, heap buffer overflow/underflow, use-after-free, invalid/double-free, and uninitialised-value use could all pass silently.

Output parsing uses valgrind's default text-mode stderr output (headline + call-stack frame lines), classified into `BugPattern`s with severity mapping (definite leak/invalid read/write/free → HIGH/CRITICAL, possible/indirect leak/uninitialised → MEDIUM). **One parsing bug found and fixed during testing:** the initial version matched "indirectly lost"/"possibly lost" as substrings anywhere in the output, which false-positived on valgrind's own `LEAK SUMMARY:` aggregate section (e.g. `indirectly lost: 0 bytes in 0 blocks` - a *summary line with a zero count*, not a finding). Fixed by requiring the actual per-error headline format (`"N bytes in M blocks are ... lost"`) and stopping the parse loop once the `LEAK SUMMARY:`/`ERROR SUMMARY:` section begins.

Verified against four real programs (leak, clean, heap buffer overflow, double-free) - each parses to the correct `BugPattern`(s) with the correct source location, and the clean program produces zero false positives. Verified end-to-end through `CDebugger.debug()` (not just `ValgrindRunner` standalone): a real leak now surfaces as `risk_level=HIGH`, findings from both the CSA static analyzer and valgrind together.

### 11.5 New: cppcheck integration into `cpp_debug` - DONE

Added `src/cpp_debug/cppcheck_analyzer.py` (`CppcheckAnalyzer`, `cppcheck_available()`), wired into `CppDebugger.debug()` as an additional detection pass merged via the existing `classifier.merge_and_dedupe()`. Rationale: cppcheck uses dataflow-based analysis rather than CSA's path-sensitive AST diagnostics, so it's a genuinely different (only partially overlapping) detector, not a duplicate of Clang's own `--analyze`. Uses cppcheck's `--xml --xml-version=2` output (parsed via `xml.etree.ElementTree`) rather than regex-parsing human-readable text, for the same stability reason CBMC/valgrind parsing elsewhere in this suite favors well-defined formats. A curated `_CRITICAL_IDS` set (`memleak`, `doubleFree`, `useAfterFree`, `nullPointer`, `arrayIndexOutOfBounds`, `bufferAccessOutOfBounds`, `uninitvar`) promotes cppcheck's own severity for these specific checks to CRITICAL, matching how the same bug classes are treated elsewhere in the suite (valgrind, CSA).

Verified against the same real leak used in §11.4: caught independently as `cppcheck_memleak` at the correct line, alongside (not duplicating) the CSA-derived `memory_leak` finding from `_design_review`/CSA - `merge_and_dedupe`'s `(location, pattern_type)` dedup key correctly treats these as distinct findings since `pattern_type` differs, which is the intended "second opinion" behavior rather than silent duplication.

### 11.6 Real bug found, FIXED this session (was documented-but-not-fixed as of v2.6.0): three separate `RiskLevel` enum classes

**Status update: fixed.** The original write-up of this finding (unchanged below for the record) recommended "pick `common.interop.RiskLevel` as canonical... and re-verify `MasterDebuggerV5`'s own risk classification logic still round-trips correctly." Did exactly that:

- `src/master_debugger/types.py`: removed its own lowercase-valued `RiskLevel(Enum)` definition, now imports `RiskLevel` from `..common.interop`. `orchestrator_v5.py`, `phases.py`, and `master_debugger/__init__.py` all import `RiskLevel` from `.types`, so they picked up the canonical class with no changes needed to those files. Checked every use of `.value` and dict/pattern-matching logic in `orchestrator_v5.py` (`classify_risk()`, `select_phases()`, `_calculate_metrics()`) first - all identity-based (`RiskLevel.CRITICAL` member comparisons and dict keys), none depended on the actual string casing, so this was safe.
- `src/master_debugger/orchestrator.py` (see new finding below - this turned out to be **dead code**, not a live call path) had its own *third* `RiskLevel(str, Enum)` definition. Fixed for consistency (zero behavioral risk, since nothing imports this module).
- **One real test had to be updated, not just left alone:** `src/tests/test_integration.py::test_critical_code_full_workflow` asserted `report.risk_level.value == 'critical'` (lowercase) - this is the exact place the old, now-removed lowercase value was being relied upon. Updated to `'CRITICAL'` with an inline note explaining why the value changed. This is a deliberate, understood behavior change verified against the fix, not a silent regression - confirmed by grep across `tests/`/`src/*/tests/` that no other test depends on lowercase risk-value strings.
- Verified end-to-end: `src.RiskLevel is common.interop.RiskLevel` (literally the same class object now), `RustDebugger`/`CDebugger`/`CppDebugger`/`AssemblyDebugger` reports compare correctly against `src.RiskLevel.X`, and `MasterDebuggerV5.debug()`'s own classification round-trips correctly (tested against real critical-risk code, produces `risk_level=CRITICAL`, summary text now reads "Risk: CRITICAL" instead of "Risk: critical" - cosmetic, not a behavior change, since that string was only ever used for a human-readable summary, never parsed back).
- Full pytest suite re-run after the fix: **359 passed, 1 deselected, 0 failed** - identical pass count to before the fix, confirming no new regressions from the unification.

Original finding (kept for the record, now resolved):

There are three independent `RiskLevel` enum definitions in the codebase:

| Location | Values |
|---|---|
| `src/common/interop.py` | `"CRITICAL"`, `"HIGH"`, `"MEDIUM"`, `"LOW"` (uppercase) |
| `src/master_debugger/types.py` | `"critical"`, `"high"`, `"medium"`, `"low"` (lowercase) |
| `src/master_debugger/orchestrator.py` | a third `class RiskLevel(str, Enum)` definition |

`src/__init__.py`'s top-level `RiskLevel` export (unchanged from the original v1.0.0 file - `from src.master_debugger.orchestrator_v5 import ..., RiskLevel, ...`) is `master_debugger.types.RiskLevel`. But `RustDebugger`, `CppDebugger`, `CDebugger`, and `AssemblyDebugger` all construct their reports via `common.interop.UnifiedDebugReport`, so their `.risk_level` attribute is actually a `common.interop.RiskLevel` instance. Both print identically (`repr()` → `"RiskLevel.CRITICAL"`), so this is invisible in casual testing/logging, but `==` silently fails across the two classes - `report.risk_level == src.RiskLevel.CRITICAL` is `False` even when the report genuinely is critical, if `report` came from any of the four language-specific debuggers rather than `MasterDebuggerV5`.

This is exactly the failure mode the suite's own `CHANGELOG.md` 2.2.2 entry already describes and partially fixed (`master_debugger/orchestrator.py`'s `_phase_2_formal()` comparing "two *different* `RiskLevel` enums... which silently fail equality checks since they're different classes with different values") - but that fix addressed one call site, not the underlying duplication, which is why it resurfaced here in a different call path (the new top-level `__init__.py`'s public API surface, exercised by any downstream code doing `from src import RiskLevel` and comparing against a per-language debugger's report).

### 11.7 New finding while fixing 11.6: `master_debugger/orchestrator.py`'s `MasterDebugger` class is dead code, and may be a more capable v6 that was never wired in

While tracing every `RiskLevel` usage to fix §11.6, found that `src/master_debugger/orchestrator.py` defines a `MasterDebugger` class (374 lines, module docstring says "Master-Debugger v6 4-phase orchestration with PyProver integration") that is **not imported anywhere in `src/` or `tests/`** - confirmed by `grep -rln "MasterDebugger\b"` across the whole tree, only the defining file itself matches. The only `MasterDebugger` actually wired into `src/__init__.py` and exercised by the test suite is `MasterDebuggerV5` (`orchestrator_v5.py`), whose `classify_risk()` is keyword/pattern matching over the raw code string, with no real per-language dispatch.

`orchestrator.py`'s unused `MasterDebugger`, by contrast, directly imports and calls `RustDebugger`, `CppDebugger`, and `PyProverBridge` (`_phase_2_formal` awaits `invoke_pyprover`), suggesting it's a real, more integrated attempt at formal-verification-aware orchestration that predates or was meant to supersede v5's phase logic - the module docstring's "v6" naming next to a package that otherwise tops out at "v5" in every exported name is itself a signal something didn't get finished or merged.

**Not investigated further or wired in this session** - this is a genuine "which orchestrator is canonical" architecture question (does v6 fully supersede v5, is it tested/working, does merging it change `MasterDebuggerV5`'s public behavior in ways downstream callers depend on) that deserves its own session rather than a decision buried inside a RiskLevel bugfix. Also has its own `UnifiedDebugReport` and `Issue` dataclasses (a *third* independent `UnifiedDebugReport` definition, distinct from `common.interop.UnifiedDebugReport` used everywhere else) - if this class is ever wired in, that duplication needs the same treatment `RiskLevel` just got.

### 11.8 Suggested libraries: status update - bandit, semgrep, and lief now wired in; tree-sitter still not

Original write-up (kept for the record): verified as installable but not wired into any module in the previous session -

- **semgrep**, **bandit** (pip) - multi-language pattern-based static analysis / Python-specific security linting. Could strengthen or partially replace the regex-based `bug_patterns.py` (python_debug) / `bug-patterns.js` (javascript_debug).
- **lief** (pip) - richer ELF/PE/Mach-O binary parsing than `pyelftools` alone, would strengthen `dwarf_analyzer.py`.
- **tree-sitter** + **tree-sitter-languages** (pip) - uniform incremental-parser AST access across most of the suite's 12+ target languages, would let structural analysis be shared rather than each module hand-rolling its own text/regex parsing.

**Status: bandit, semgrep, and lief are now all installed, wired in, and verified against real code.** See §11.10-§11.11 (bandit/semgrep) and §11.14 (lief). `tree-sitter` remains uninstalled/unwired - it's a suite-wide parsing-strategy change (touching how every language module represents source structure), not a single-module addition, and wasn't attempted. Confirmed still pip-installable (checked in an earlier session) but not re-verified by installing it.

### 11.9 Real bug found while verifying the bandit fix: `MasterDebuggerV5.debug()` can hang indefinitely if traced code calls `input()`

While testing the bandit fix (§11.11) end-to-end through `MasterDebuggerV5.debug()`, a test using genuinely vulnerable code that happened to include `input()` (`subprocess.call("rm -rf " + input(), shell=True)`) hung the sandbox past a 60s command timeout. Isolated by removing the `input()` call, which resolved it immediately - `MasterDebuggerV5`'s Phase 1 (`Phase1RuntimeDebug`) genuinely *executes* the traced code (this is how `python_debug`'s execution-tracing approach works - it's not purely static), and in this sandboxed environment there's no interactive stdin, so `input()` blocks forever waiting for input that will never arrive.

**Not fixed this session** - this is a real, separate finding from anything else in this session's scope (touches `python_debug`'s core execution engine, not Phase 0/RiskLevel/the new analyzer modules), and a proper fix needs a design decision: wrap traced execution with a timeout (kills the process but loses partial trace data), monkeypatch/mock `input()` to return a sentinel value during tracing (changes program behavior, could mask real bugs downstream of the `input()` call), or redirect stdin from `/dev/null` (fails fast with `EOFError` instead of hanging, probably the least invasive option, but changes what exception the traced code raises compared to real interactive use). Recorded here as a concrete finding for a future session rather than a guessed fix under time pressure. Reproduction:

```python
import src
md = src.MasterDebuggerV5()
report = md.debug("x = input('enter something: ')\nprint(x)\n")  # hangs indefinitely, no timeout
```

### 11.10 Real bug found and fixed: bandit was already wired into `Phase0StaticAnalysis`, but its detection check never matched real bandit output

Similar to CBMC/cppcheck in §11.9 - this wasn't a missing feature, it was dormant, broken code that had apparently never been exercised against a real bandit install. `master_debugger/phases.py`'s `Phase0StaticAnalysis.run()` already called `bandit` via subprocess and had a `StaticAnalysisResult.bandit_warnings` field ready to receive results - but the check `if 'WARNING' in output.stdout or 'SEVERITY' in output.stdout` never matches real bandit 1.9.4 text output, which says `"Severity:"` (mixed case) and `"Issue:"`, never the all-caps strings this checked for. Combined with the existing `except (subprocess.TimeoutExpired, FileNotFoundError): pass`, "bandit isn't installed" and "bandit ran and found nothing" were indistinguishable - and since bandit was apparently never installed in whatever environment last touched this code, real security findings were silently discarded on every single run.

Installed bandit 1.9.4 via pip, confirmed the broken match against genuinely vulnerable code (hardcoded password + `subprocess.call(..., shell=True)` - both textbook bandit findings, B105/B602, neither surfaced). Fixed by switching to `bandit -f json` for structured, stable parsing (same rationale as cppcheck's `--xml` and the general pattern established this session: don't regex-match human-readable tool output when a structured format is available). Verified: real findings now surface correctly (`[B404]`, `[B105]`, `[B602]` with correct severity and line numbers), zero false positives on clean code, and the fix round-trips through `MasterDebuggerV5.debug()` end-to-end. mypy and pylint's existing wiring in the same function were checked too and both already work correctly against real installs (mypy 2.2.0, pylint 4.0.6) - only bandit's match condition was broken.

### 11.11 New: semgrep integration into `Phase0StaticAnalysis` - DONE, with real constraints found and worked around

Added `src/common/semgrep_analyzer.py` (`SemgrepAnalyzer`, `semgrep_available()`), wired into `Phase0StaticAnalysis.run()` alongside mypy/pylint/bandit, plus a new `StaticAnalysisResult.semgrep_findings` field. Rationale: semgrep's checks are declarative pattern rules from a different rule-authoring lineage than bandit's hand-coded AST visitors, so it's a genuine "second opinion" in the same spirit as `CppcheckAnalyzer` alongside Clang (§11.5), not a duplicate.

Two real constraints discovered and worked around, not just installed-and-done:

1. **`semgrep --config auto` (and any `p/`/`r/` registry config) requires network access to `semgrep.dev`, which returned `HTTP 403` when tested from this sandbox.** The suite's network allowlist covers `github.com`/`codeload.github.com` but not `semgrep.dev`. Worked around by downloading the `semgrep/semgrep-rules` repository directly from GitHub as a tarball (same pattern as the CBMC `.deb` GitHub-release download in the previous session) and bundling a rule subset directly in the skill package at `src/common/semgrep_rules/`, with a `README.md` there documenting provenance, license (Semgrep Rules License v1.0, copied verbatim), and how to refresh/expand the bundled rules. `SemgrepAnalyzer` always points `--config` at this local directory, never at a registry shorthand.

2. **Rule-compilation overhead scales with rule count and is significant**: the full `python/lang/security/` subset (91 rules) took ~17s per scan regardless of input size (measured via direct timing, not estimated) - far past the ~5-10s budget every other Phase 0 tool uses, and with no caching benefit on repeated runs. Trimmed to a curated 20-rule subset (~6-7s per scan) covering distinct threat categories with minimal overlap with bandit: command injection, unsafe eval/exec, unsafe deserialization, SQL injection, XXE, weak crypto, TLS/cert issues, ReDoS, reverse shells, credential handling. Verified detection still works across 4 of these categories against genuinely vulnerable code (`pickle.loads`, `hashlib.md5`, `eval()`, catastrophic-backtracking regex) with zero false positives on clean code, before finalizing the trimmed set - the full rationale and category list is in `semgrep_rules/README.md`.

**Known tradeoff, not fully resolved:** even at 20 rules, semgrep adds a fixed ~6-8s to every `Phase0StaticAnalysis.run()` call (subprocess startup + rule compilation dominate, not the actual scan), regardless of code size. This is a real, noticeable latency cost for interactive use, and it roughly 4-6x'd the formal pytest suite's total runtime (from ~10-17s to ~60s, since `test_orchestration.py`/`test_integration.py` call `MasterDebuggerV5.debug()`/`Phase0StaticAnalysis.run()` multiple times each). Not addressed this session - options for a future pass: make semgrep opt-in via a parameter rather than always-on, investigate `semgrep --time` profiling to see if rule-compilation can be cached across invocations (e.g. a long-lived `semgrep` daemon mode, if one exists), or trim the rule count further. Flagging honestly rather than leaving this as a silent regression.

Full pytest suite re-run after both §11.11 and §11.12: **359 passed, 1 deselected, 0 failed** (same pass count as before - the ~50s slowdown is real but did not break anything).

### 11.12 Two more real bugs found by actually running the formal pytest suite (both fixed, previous session)

Running `pytest tests/ src/ -q` after §11.1-11.5's changes surfaced 2 failures out of 359 collected tests. Neither was caused by that session's edits, but both were only reachable because that session installed cppcheck and CBMC for the first time (see §11.2) - the relevant tests are `@pytest.mark.skipif`-gated on tool availability and had presumably never run against a real toolchain in whatever environment last produced the "355/355 passing" CHANGELOG figure.

**Bug A - self-inflicted, fixed immediately (see §11.5):** the new `CppcheckAnalyzer`'s own `--suppress=missingIncludeSystem` flag generated a benign `unmatchedSuppression` info-level finding on trivial code with no includes, which the *existing, unchanged* risk classifier (`elif all_patterns: risk = MEDIUM`) treated the same as a real finding - pushing `test_debug_clean_code_low_risk` from LOW to MEDIUM. Fixed by also suppressing `unmatchedSuppression` itself.

**Bug B - pre-existing, unrelated to this session's other work, fixed:** `TestCBMCIntegration::test_div_zero_detected` failed because `CBMCDriver.BASE_FLAGS` in `symbolic_executor.py` used `--null-pointer-check` and `--overflow-check`, which CBMC 6.x renamed/split (`--pointer-check`, `--signed-overflow-check` + `--unsigned-overflow-check`). This is a hard CLI usage error in CBMC 6.x, not a soft deprecation - CBMC refuses to run *any* check and prints its help text instead. Because `_parse_cbmc_output` correctly finds zero matching lines in help text, `SymbolicExecutor` was reporting `cbmc_ran=True` with zero findings for every single input on any CBMC 6.x install, indistinguishable from "ran cleanly, no bugs found." The one test that would have caught this either way (`test_safe_program_no_findings`, asserting zero findings on safe code) couldn't distinguish "correctly found nothing" from "silently never checked anything," which is exactly why `test_div_zero_detected` (asserting a finding *is* produced on genuinely broken code) is the test that actually caught it.

Fixed by updating `BASE_FLAGS` to the CBMC 6.x flag names, verified against the real installed CBMC 6.10.0 with a manual `--unwind 5 --bounds-check --div-by-zero-check --pointer-check --signed-overflow-check --unsigned-overflow-check --pointer-overflow-check --memory-leak-check` invocation before touching the source, confirming it now catches a real division-by-zero (`division-by-zero.1 ... FAILURE`).

**This means the "355/355 passing" figure in `CHANGELOG.md`'s v2.5.0-era entries was never exercising CBMC or cppcheck against a real toolchain** - both are gated `skipif(not tool_available())`, and if neither was installed in whatever environment produced that number, the entire CBMC integration path (all of Phase 6's CBMC half) could have been silently broken for an unknown number of releases without any test failure signal. Worth a note for whoever next touches this suite: **installing the optional tools and re-running the suite is not just "nice to have" coverage, it's the only way several of these integration paths get exercised at all.** (This lesson repeated itself twice more in the same-day follow-up session - see §11.10's bandit finding and the CBMC pattern is structurally identical.)

### 11.14 New: lief integration into `cpp_debug` - DONE, with a self-inflicted classifier regression found and fixed

Added `src/cpp_debug/lief_analyzer.py` (`LiefBinaryAnalyzer`, `lief_available()`), wired into `CppDebugger.debug()`. Deliberately **not** a replacement for `pyelftools` in `dwarf_analyzer.py` - the two serve different purposes. `pyelftools`' DWARF module walks compiler-emitted debug info (DIEs) to recover variable types/locations/pointer-escape patterns; lief doesn't have comparable DWARF depth. What lief is actually good at, and what `DWARFAnalyzer` doesn't check at all, is binary-format-level hardening posture (PIE/NX/RELRO/stack-canary) and the imported-symbol table - flagging use of classically dangerous libc functions (`system`, `strcpy`, `gets`, ...) straight from a compiled binary's import table, without needing source access. Verified both directions with real compiled binaries: PIE/NX/RELRO/stack-canary detection toggles correctly between a default build and one deliberately weakened with `-fno-stack-protector -Wl,-z,norelro`, and dangerous imports (`system`, `strcpy`) are correctly listed from a real binary's own import table.

**Self-inflicted bug found and fixed during verification**, same pattern as the cppcheck `unmatchedSuppression` regression in §11.9's Bug A: the `missing_stack_canary` hardening finding is real and accurate (this sandbox's `clang` genuinely doesn't enable stack-protector by default, unlike `gcc`), but it's a property of the compiler/linker flags used, not of the code's content - it fires on essentially *any* input compiled the same way, including the formal test suite's trivial `int main() { return 0; }` clean-code case. The existing, unchanged risk classifier (`elif all_patterns: risk = MEDIUM`) doesn't distinguish "any finding" from "a finding that actually says something about this code," so `test_debug_clean_code_low_risk` regressed from LOW to MEDIUM exactly the same way it did with cppcheck's suppression noise.

**Fix, more structural than the cppcheck one:** split `LiefBinaryAnalyzer.analyze()` into two channels via an `include_hardening` parameter - dangerous-import findings (a real property of what the code does: does it call `system()`/`strcpy()`) vs. hardening-posture findings (a toolchain-constant property, not code-content-dependent). `CppDebugger.debug()`'s automatic pipeline calls `analyze(code, include_hardening=False)`, so only dangerous-import findings feed the shared risk classifier. The full hardening audit (all four checks) is still available by calling `LiefBinaryAnalyzer().analyze(code, include_hardening=True)` directly - nothing was removed, just kept out of the path that drives automatic per-code risk scoring. Verified all three states after the fix: clean code → `LOW` risk with zero patterns; vulnerable code (`strcpy`+`system`) → `CRITICAL` risk with `dangerous_import_system`/`dangerous_import_strcpy` correctly present; direct full-audit call on clean code still surfaces `missing_stack_canary` for anyone who wants the complete hardening picture.

Full pytest suite re-run after the fix: **359 passed, 1 deselected, 0 failed** - same count as before lief was added, confirming the fix fully resolved the regression with no other side effects.



### 11.15 Final version/test-suite state after all sessions

`src/__init__.py`: v2.6.1, 61 exports. `c_debug/__init__.py`: v1.1.0. `cpp_debug/__init__.py`: v1.4.0. `master_debugger/types.py`: `RiskLevel` now imports from `common.interop` (§11.6) rather than defining its own. `master_debugger/phases.py`: bandit fixed, semgrep added (§11.9-11.10). New files: `common/semgrep_analyzer.py` + bundled `common/semgrep_rules/` (20 curated rules, 108KB); `cpp_debug/lief_analyzer.py` (§11.14).

Ad-hoc smoke test (not part of `tests/`, used across both sessions to verify changes against real installed tools): 20/20 passing.

**Formal `tests/`+`src/` pytest suite: 359 passed, 1 deselected, 0 failed** (`python -m pytest tests/ src/ -q`), confirmed after every change across all sessions, most recently after the lief integration and fix (§11.14) - same pass count throughout every single change in this document, confirming no regressions were introduced by any of this work. Full suite runtime increased from ~10-17s to ~50-70s due to semgrep's per-invocation overhead (§11.11) - a real, disclosed tradeoff, not a silent one. The 1 deselected item is a pre-existing marker-based exclusion, not investigated (out of scope).

**Summary of what's fixed vs. what remains, across all sessions:**

| Item | Status |
|---|---|
| `src/__init__.py` empty | Fixed |
| `test_generator` broken import | Fixed |
| `RustDebugger` false-confidence | Fixed |
| CBMC 6.x flag incompatibility | Fixed |
| cppcheck suppression false-positive | Fixed |
| Three `RiskLevel` enum classes | Fixed |
| bandit detection never matching | Fixed |
| lief hardening-posture false "risk" on any input | Fixed |
| valgrind integration | Added |
| cppcheck integration | Added |
| semgrep integration | Added |
| lief integration | Added |
| `MasterDebugger` v6 dead code / 3rd `UnifiedDebugReport` | Found, not fixed (needs its own session) |
| `input()` hang in `MasterDebuggerV5.debug()` | Found, not fixed (needs a design decision) |
| KLEE unavailable | Documented, not fixable in this environment |
| `tree-sitter` | Documented, not attempted |
| semgrep's ~6-8s per-call overhead | Documented, not resolved |
