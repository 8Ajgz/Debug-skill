# Debug-Suite Roadmap

**Current version:** 2.9.6 base, with the changes listed in CHANGELOG `[Unreleased]`. Version strings were reconciled in the `Current state` section below.
**Last updated:** 2026-07-11 (§21 added — real-world Rust test, a genuine `rust_debug` false-positive fixed, `troubleshooting` domain-awareness merge, full stub inventory in `STUBS.md`)
**See also:** `debug-suite-handoff.md` (regenerated 2026-07-11 alongside this update — read it first for "what to do next"; read this file for the full reasoning behind any of it) and `STUBS.md` (new 2026-07-11, full stub/placeholder inventory referenced from §21.7).
**This document supersedes:** the original `debug-suite-v2_1` Phase 1-3 roadmap (reproduced in §9 below, updated with current status)
**Compiled:** June 30, 2026, from a full conversation-history search across every component skill that was merged into this suite (pyprover, python-debug, master-debugger, test-generator, code-orchestrator, troubleshooting, standardize-skill)

---

## Current state (read this first)

**Last updated:** 2026-10-20, after the PyProver result-soundness series (see the first `Done since 2.9.6` entry). Earlier: 2026-10-19, after the design-review error fix on `main`. Everything in the sections below this one is history, and some of it is out of date. Where they disagree, this section and the three docs it names win.

**Read in this order:**
1. `docs/FEATURE_AUDIT.md`: status of every old feature (incorporated, partial, superseded, not incorporated, never built, unverifiable), with the file that holds each one, and the open items in priority order.
2. `docs/EVOLUTION.md`: the 13 archive releases that were replayed as history, the component lineages, and the feature-loss audit.
3. `CHANGELOG.md` `[Unreleased]`: everything changed since 2.9.6.
4. The rest of this file only for the reasoning behind a specific decision.

**Where the code is:**
- Repo: `8Ajgz/Debug-skill`, branch `main`. Base is debug-suite 2.9.6, with later changes on top. The history is 13 release commits (1.0.0 to 2.9.6, dated to each release, with 2.0.0 inferred) followed by the work in this file.
- The original archive zip (114 entries, about 23 MB) is on branch `archive` of the same repo, as an orphan branch with no code. It is not part of the skill. To unpack, use zip-safe extraction into an empty directory, and run any Python that reads it with `python -I`.

**How to verify:** `python -m pytest -q -p no:cacheprovider` from the repo root. Plain `pytest` works (`pytest.ini` sets the import path). Last run: 916 passed, 58 skipped, 1 deselected (2026-10-19, this sandbox). Skips are optional tools (semgrep, bandit, clang, cppcheck, valgrind, CBMC, KLEE, angr) and the Node and Rust tests when `node` or `rustc` is missing. The earlier count of 934 passed, 22 skipped came from a fuller environment. The JS and Rust property tests need `node` and `rustc`. Hypothesis is optional for Python property tests.

**Done since 2.9.6** (details in CHANGELOG `[Unreleased]`):
- PyProver result soundness (6 commits, 2026-10-20): a postcondition on `result` is now checked against the body, not only for satisfiability. Before, `Post: result < 0` for `return x * 2` with `Pre: x >= 0` reported VERIFIED, and so did code with no annotations. Now: the inliner (`contract_verifier.py`) handles assignments, `if`/`else` and constant `range()` loops; `src/pyprover/loop_vc.py` handles `while` loops, `for` over arrays or symbolic ranges (with `# Invariant:`), array and attribute writes, call statements (which havoc arrays, fields and globals), returns inside loops, and paths that fall off the end. Writes to two or more arrays or objects are checked under every aliasing grouping (up to four parameters). Anything not proven is INCONCLUSIVE, never a pass; a model counterexample is downgraded to unproven rather than reported as a failure. Regression tests: `src/pyprover/tests/test_result_soundness.py`, `test_loop_vc.py`.
- PyProver: SHA256 cache, parallel batch verification (worker processes, not threads, because Z3 is not thread-safe), SMT-LIB export via `to_smt2()`, Hypothesis property tests (Python), invariant templates (6 of the 8 v8.2 ones), conditional postconditions (`if cond: clause`), float precision (Z3 Real, real division), decorator contracts (`@requires`, `@ensures`, `@loop_invariant`), quantified loop invariants (`all`/`any` over `range` as ForAll/Exists), and property testing for JavaScript (node) and Rust (rustc).
- Loop verifier: INIT is checked as validity at the entry values read from the source. It was satisfiability before, which reported `i >= 0` as verified with i starting at -1. Unknown entry or no iteration variable gives `None`, not `True`.
- Master debugger: `verify_fix()` (bug reproduced on the original, fix passes on the new code), for Python, JS and Rust. It is a function the caller invokes, not an automatic step in `debug()`.
- Master debugger phase 5: a test-generator failure is recorded in `UnifiedDebugReport.test_generation_error` and printed to stderr. It used to be dropped silently (`except Exception: pass`), which left an empty `test_suite` indistinguishable from "no tests needed". Covered by `tests/test_master_debugger_phase5.py`.
- Master debugger static phase: bandit crashes, bandit timeouts, unparseable bandit output, mypy and pylint timeouts (which used to read as "no errors", so `passed` was True) and semgrep exceptions are recorded in `StaticAnalysisResult.tool_errors` and reported as `static_tool_error` issues, so they cannot produce a VERIFIED verdict. Bandit and semgrep findings were computed but never copied into the report's issues, so they could not change the verdict; they now do. A tool that is not installed is still a skip. `MasterDebuggerV5` (the class exported at the top level) had the same gap: it ignored bandit, semgrep and tool errors, and counted a timed-out mypy as a passed phase, so confidence read 1.0. It now counts them, and a phase with a failed tool does not pass.
- Master debugger runtime phase: when the python-debug tracer itself raised, the failure was stored in `RuntimeDebugResult.exceptions` and nothing else read it, so the run reported no issue (and could reach VERIFIED if pyprover passed). It is now `RuntimeDebugResult.tool_error`, reported as a `runtime_tool_error` issue and counted by V5. A traced program's own exceptions are not tool errors. Covered by `tests/test_master_debugger_static_tools.py`.
- Master debugger concurrency check: when PyProver's `verify_async` raised, `_phase_2_async` returned no findings, so a passing formal check read as ✅ VERIFIED (reproduced with a stub bridge, confidence 0.95). It now returns an `async_tool_error` issue.
- Master debugger formal check: when PyProver's `verify` raised, `_phase_2_formal` returned `None`, which the caller treats as "not available", so the formal phase was listed as completed and the failure reached the verdict only as INCONCLUSIVE. It now returns a `tool_error` marker, reported as a `formal_tool_error` issue, and the phase is not marked completed. Covered by `tests/test_master_debugger_static_tools.py`.
- Master debugger Python phases: an exception escaping Phase 0, 1 or 3 was printed and then ignored, so the run could still reach a verdict with none of that phase's findings. It is now an `analysis_error` issue. Covered by `tests/test_master_debugger_static_tools.py`.
- Master debugger design review: a crashed review was reported as `design_review_failed` with a pointer to a `phase_3_design` field the report does not have, so the error was lost. It is now `design_review_error` with the error text. A real design finding names the classification and first remediation step. Covered by `tests/test_master_debugger_static_tools.py`.
- Python debug: last-line assignments are recorded (the FIXED build's behaviour, plus the fallback to the last traced line). `get_variable_mutations()` no longer crashes on events without a snapshot.
- Rust: `rustc` no longer writes a binary into the working directory. Four such binaries that the archive had committed were removed.
- Pytest: `pythonpath = src .` in `pytest.ini`. Version strings agree at 2.9.6 in SKILL.md, INTEROP.yaml, MANIFEST.txt, openapi.yaml, API.md, README and `src/__init__.py`.

**Decisions and why** (do not reopen without new evidence):
- Unproven is never a pass. Any path the model cannot judge (unsupported statement, no invariant, invariant not inductive, bare array or object used as a value, a path that may fall off the end) gives `verified: false` with `inconclusive: true`. A counterexample from the loop model is downgraded to unproven, because havoc and index bounds can produce states no real run reaches.
- Loop invariants are `# Invariant:` comments directly above the loop. Each proof obligation may use only the premises established before it, so a loop's exit fact cannot justify its own invariant.
- Z3 runs in worker processes, not threads (thread-unsafe global context).
- Floats are Z3 Real. Python `/` is real division. `//` and `%` are skipped over reals, since their semantics differ.
- Invariant templates are checked by running reference loops, not proved. Z3 does not model subscripts, `len` or `sum`. RECURSION (its `base OR step` form is not an invariant) and WHILE_LOOP (its bound is a guess) were dropped.
- The v7 SMT-LIB, Coq and Lean exporters were stubs. SMT-LIB was re-done from Z3. Coq and Lean are not ported.
- tree-sitter: no-go for the suite-wide framing (roadmap 12.2).
- Contracts are Python-syntax text in every language (comments or decorators). The per-language adapters from v10 and v11 are not wired in.
- Property testing executes the code under test. Use it only on trusted code.

**Open items, in priority order** (full list with reasons in `docs/FEATURE_AUDIT.md`):
1. Remaining decorators from the old code: `@contract`, `@ghost_variable`, `@pure_function`, `@applies_contract`, `@auto_validator`, `@with_runtime_safety`.
2. Per-language contract parsing for Go, Java, C#, TypeScript and WebAssembly, and property tests for those languages.
3. Loop verifier model: it checks one `i += 1` step. It does not model the loop body or arrays, so PRESERVATION is weaker than the name suggests.
4. ASan and UBSan runtime checks (layer 2 of the five-layer stack).
5. Counterexample-driven test generation. The roadmap says it exists in `test_generator`, but the code does not have it.
6. Developer tooling (Makefile, ruff, black, pytest-benchmark) and the eight v12.2 example scripts.
7. Re-run the standardize-skill security audit (roadmap 2.6). Not done.
8. Silent `except` handlers in `assembly_debug` (`symbolic.py`), `cpp_debug` (`lief_analyzer.py`, `dwarf_analyzer.py`) and `code_orchestrator`. Only `master_debugger` was traced. Check each for a path to a verdict before changing it. `code_orchestrator` is not on the master debugger verdict path (checked 2026-10-19). `LiefBinaryAnalyzer` is exported but not called by the verdict pipeline.
9. CLOSED 2026-10-20: the mapping in `_phase_2_formal` agrees with the bridge. The real defect was upstream: `ContractVerifier.verify_contract` reported verified=True for a false postcondition on `result` (satisfiability only) and for code with no annotations. Fixed in `contract_verifier.py`: the return expression is substituted for `result` when the body is a single `return`, and anything unproven is INCONCLUSIVE. Regression tests in `src/pyprover/tests/test_result_soundness.py`. Inlined: assignments, `if`/`else`, constant `range()` loops (up to 16 iterations), and pure builtin calls as statements. Loops, arrays and objects run through `src/pyprover/loop_vc.py`, with a `# Invariant:` comment directly above the loop. In an invariant, a `for` loop variable means the current index (or element). Returns inside loops, calls used as statements (which havoc arrays, object fields and free globals), attribute writes, and paths that fall off the end are modelled. Aliasing: when arrays or objects are written (or a call can change them), every grouping of up to four accessed parameters into one object is checked, and a result must hold in all of them. Still unproven: five or more such parameters, and a bare parameter returned as a value when neither the code nor a clause shows it is a number (`return arr` with only `Pre: len(arr) > 0`).

**Handoff (for the next instance, written 2026-10-19):**

- *How this session worked:* each fix followed one loop. Find a silent failure on the verdict path, reproduce it with a fake tool or stub (on PATH, or monkeypatched), fix it, add a test that fails on the old code (`git stash push -- <file>` then rerun), run the full suite, update this section and `CHANGELOG.md`, commit on a branch, fast-forward `main`, and `git push origin main`. Verify with `git rev-parse --short HEAD` and `origin/main` after `git fetch`.
- *Environment:* the repo is cloned at `/home/user/debug-skill`. Packages needed for the suite: `pytest`, `hypothesis`, `z3-solver` (`pip install`). Without `z3-solver`, three `src/pyprover/tests` modules fail at collection. Skip count depends on which optional tools are installed (`bandit`, `semgrep`, `lief` were absent in the last sandbox).
- *Test patterns in use:* `tests/test_master_debugger_static_tools.py` holds the regression tests. Fake external tools are written as shell scripts into a `tmp_path` that is prepended to `PATH` (`_fake_bandit`, `_fake_slow_mypy`). Stubs replace `MasterDebugger.pyprover_bridge`. Monkeypatched module attributes are read at call time. Imports use `from src.<pkg> ...`, not the relative form.
- *Decisions made in this session (do not reopen without new evidence):*
  - A tool that is not installed is a skip. A tool that ran and failed is a `*_tool_error` issue. A traced program's own exceptions are not tool errors.
  - A phase with a failed tool does not pass.
  - Fixes go through the verdict path (`orchestrator.py` and `orchestrator_v5.py`), not only the phase classes.
  - Commit trailer: the user asked for `Co-Authored-By: Claude Haiku 5.5 overseen by Maxwell Morrongiello`, which overrides the "no model identifier" rule for this repo. Earlier commits used a generic `Claude` trailer.
  - Commits are not pushed unless the user asks, though this repo's convention is a fast-forward push to `main`. The user asked for merges to `main` in later rounds, and those were done.
- *Open from this session:* item 8 above. Also `_phase_2_formal` does not record its reason on the report when it is unavailable, only when it crashes.
- *Budget note:* the user was tracking a usage limit (7% then 6%). Each fix took roughly 6 to 10 tool calls. Keep the roadmap edits to one read and one edit per line.

**Known gaps, not yet triaged:**
- The old code had a `TemplatesMatcher` that chose the invariant template from the code. The repo has no equivalent, so templates have to be picked by hand.
- The old `VerificationReport` and `Contract` had `to_dict` and `from_dict`. The repo has no serialization for pyprover reports.
- `pyprover_bridge` JSON now carries `null` for loop `init_holds` and `preservation_holds` when they are unknown. Consumers outside this repo have not been checked.

**Workflow notes:**
- Never delete tracked files, and never rebuild history, without confirming first. The auto-mode classifier blocked one history rebuild until the user approved it explicitly.
- `main` only moves forward. Commits are pushed with plain `git push` (fast-forward). No force pushes.
- Commit trailers: `Co-Authored-By` and `Claude-Session` lines, as the attribution reminder requires. The provenance note in `README.md` says all code was written by an unspecified Claude version under the oversight of Maxwell Morrongiello.
- Test artifacts: the Hypothesis plugin writes `.hypothesis/` (ignored). Rust tests once wrote binaries into the repo root (fixed, see above).

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

## §12. Branch reconciliation session (2026-07-10, v2.6.1 → v2.7.0)

### 12.0 Context and method

This session started from `debug-suite-handoff.md`'s explicit instruction: reconcile this branch (v2.6.1) with a sibling branch (v2.5.2, chat `3abe64d4-9daa-44e5-acc8-5e4e6cda9f6b`) that diverged from the same common ancestor at nearly the same timestamp, before doing anything else. Per the handoff's Past-Chat Review Instruction, ran `conversation_search` for the sibling chat and confirmed its content via two searches (`"debug-suite MasterDebugger v6 RiskLevel"`, `"_check_satisfiable skip non-boolean expression"`) rather than trusting the handoff's summary alone. The sibling chat's tool-call transcript (str_replace old_str/new_str pairs, visible directly in the search snippets) served as the diff source, since the sibling's packaged `.skill` file itself wasn't available to fetch in this session — reconstructed each fix from the transcript, not from a re-derived guess at what the fix "should" look like.

### 12.1 The four sibling fixes: three merged as-is, one required re-diagnosis

Extracted the uploaded `debug-suite.skill` (v2.6.1) fresh to `/home/claude/work/debug-suite-v261` and confirmed a clean baseline (313 passed, 46 skipped, 1 deselected in this sandbox — lower pass/higher skip count than the 359/1 the original v2.6.1 session reported, because this sandbox has fewer optional tools installed; not a branch difference, a sandbox difference).

Three of the sibling's four fixes transferred directly, since the target files were structurally identical between branches:
- `master_debugger/__init__.py`: export both `MasterDebugger` (v6) and `MasterDebuggerV5`. Verified both import cleanly post-fix (rustc/clang warnings on import are expected — those toolchains aren't installed in this sandbox, unrelated to the fix).
- `common/pyprover_bridge.py`: `_map_language_type` accepts `LanguageType` directly. Added `Union` to the typing import (the sibling's diff implied this but didn't show the import line explicitly in the retrieved transcript — inferred from the type hint itself, correct and unambiguous).
- `requirements.txt`: removed `hypothesis`. Independently re-confirmed unused via `grep -rln "import hypothesis" src/` before removing, rather than trusting the sibling's claim unverified.

The fourth — the Z3 Bool/Int bare-identifier fix in `contract_verifier.py` — did **not** transfer directly. Investigating why (rather than force-applying a patch to a file where the described bug pattern doesn't exist) surfaced a real architectural fact: **this branch's `src/pyprover/contract_verifier.py` is a 154-line stub.** Its `verify_contract()` never calls `Solver.add()` on a parsed postcondition at all — the actual body reads `"Full Z3 verification would require sophisticated SMT setup"` and just checks whether both precondition and postcondition lists are non-empty. The decorator-based `@requires`/`@ensures` contract system with a real `_check_satisfiable()` that the sibling patched isn't part of this branch's live `src/` tree — confirmed via `grep -rln "def requires\|def ensures\|_contracts\[" src/` returning only a prototype file in `legacy_code/` (not imported by anything). Force-applying the sibling's literal patch here would have edited dead code and fixed nothing.

Traced where this branch's actual Z3 implication-checking lives instead (`pyprover/contract_simplifier.py`'s `_implies()`/`_is_tautology()`, added in an earlier session, not present in whatever ancestor the sibling branched from with a full contract_verifier) and checked whether the same bug class was reachable there. It was: `_expr_to_z3()`'s `ast.Name` branch turns any bare identifier into a Z3 `Int` (`env[node.id] = z3.Int(node.id)`), never a `Bool`. Reproduced before fixing:

```
ContractSimplifier().simplify(requires=['n >= 0'], ensures=['result'])
→ Z3Exception: Value cannot be converted into a Z3 Boolean value
```

Fixed with a `_is_z3_bool()` sort-check guard (mirroring the sibling's `_is_z3_bool` helper name and approach, adapted to this branch's actual call sites) in both `_implies()` and `_is_tautology()`. Non-boolean clauses now route through the existing `"unknown"`/timeout-clause conservative-keep path rather than crashing — same soundness principle the sibling's fix used (never silently drop, never crash). Re-ran the reproduction after the fix: no crash, clause conservatively kept.

### 12.2 tree-sitter: scoped and decided — no-go for the suite-wide framing, narrow opportunity noted

The previous session (§12, first pass) deferred this without actually scoping it. Did the scoping pass this session: audited every regex-based source-parsing call site in `src/` to determine what tree-sitter would actually replace or supplement.

**Finding: this suite's regex usage falls into two buckets, and tree-sitter is the wrong tool for both of them.**

1. **Tool-output parsing, not source parsing.** `cpp_debug/diagnostics.py`'s `_DIAG_RE` parses Clang diagnostic output. `c_debug/debugger.py`'s `_STRACE_LINE_RE`/`_VALGRIND_HEADLINE_RE`/`_VALGRIND_FRAME_RE` parse strace/valgrind stdout. `assembly_debug/dataflow.py`'s register-token regex operates on an already-tokenized operand string, not multi-line source. None of these are parsing source code — tree-sitter parses source grammars, not arbitrary tool-output log formats, so it doesn't apply here regardless of how the original "documented but not implemented" library list framed it.

2. **`python_debug/bug_patterns.py`'s raw-source anti-pattern regexes** (e.g. `range(len(x)+1)`, `while i <= len(...)`, mutate-during-iteration) genuinely are matching against raw Python source, and genuinely are fragile to formatting/whitespace/comment variance the way regex-on-source always is. But Python already has a real, dependency-free structural parser in the stdlib (`ast`), which this same codebase already uses elsewhere for exactly this kind of pattern-matching (`pyprover/contract_simplifier.py`'s `_expr_to_z3`/AST walk). Adding tree-sitter's Python grammar to fix this file would mean carrying a new native-extension dependency to solve a problem the standard library already solves for free. If `bug_patterns.py`'s regex fragility becomes a real problem, `ast`-based rewrite is the right fix, not tree-sitter — but that's its own separate, smaller task, not part of a tree-sitter integration.

**Deeper reason the suite doesn't need tree-sitter for its main languages: it already delegates structural analysis to the real toolchain wherever one exists**, which is strictly better than a syntax tree. `cpp_debug/analyzer.py` shells out to the real Clang Static Analyzer (path-sensitive analysis, not just a parse tree). `rust_debug` shells out to `rustc`+`clippy`. `c_debug`/`cpp_debug` also use CBMC/KLEE (bounded model checking) and valgrind (real dynamic analysis) where installed. Confirmed via `grep -rln "import re" src/rust_debug src/javascript_debug` returning nothing — neither module hand-parses source with regex at all, because both delegate to a real toolchain (`rustc`/`clippy`; the JS module's own execution-tracing approach) instead. A syntax tree from tree-sitter would be a strict downgrade in analysis quality compared to what these modules already get from real compilers, not an upgrade.

**The one place a real gap exists:** PyProver's `ContractVerifier.parse_contract()` (or its equivalent in whichever module actually does the Z3 solving per §12.1's finding that this branch's `contract_verifier.py` is a stub) is explicitly documented as "language-agnostic text parsing regardless of declared language" — it finds `# Pre:`/`// Post:`/`/* Inv: */` comment annotations by proximity, with no real understanding of function boundaries, for any of PyProver's other 11 target languages (Go, Java, C#, WebAssembly, NASM, FASM, etc. per SKILL.md's language list). Tree-sitter has grammars for most of these and could in principle locate the actual enclosing function for a contract comment rather than assuming adjacency. This is a real, narrow, single-file opportunity — but it's marginal (comment-adjacency already works for the common case of a contract comment immediately preceding the function it describes) and not the "touches every language module" framing the original request implied.

**Decision: no-go on tree-sitter as a suite-wide integration.** The suite's existing architecture (delegate to real toolchains, use `ast` for Python, keep regex only for tool-output parsing) already captures most of what tree-sitter would offer, for the languages that matter most. Not re-opening this as a "maybe later" item — if the PyProver comment-adjacency edge case (contract comment far from its function) becomes an actual reported problem, that's a small, separately-scoped task, not a reason to revisit this suite-wide decision.

### 12.3 Test coverage added

No new pytest test files existed for `SemgrepAnalyzer`/`LiefBinaryAnalyzer` before this session (a gap the handoff explicitly flagged) — still true after this session; out of scope here, since this session's mandate was reconciliation, not closing that specific pre-existing gap. Did add regression coverage for everything touched this session:
- `src/common/tests/test_pyprover_bridge.py` (new file, 4 tests): string mapping, case-insensitivity, `LanguageType`-direct-pass, unknown-input `None`.
- `src/master_debugger/tests/test_orchestration.py`: new `TestPublicAPIExports` class (2 tests) confirming both orchestrators import and are in `__all__`.
- `src/pyprover/tests/test_verification.py`: 3 new tests in `TestContractSimplifier` (`test_bare_identifier_ensures_no_crash`, `test_bare_identifier_requires_no_crash`, `test_is_z3_bool_helper`).

Full suite after all fixes and new tests: **322 passed, 46 skipped, 1 deselected, 0 failed** — up from the 313-passed baseline by exactly the 9 new tests, confirming zero regressions from the reconciliation.

### 12.4 What did not need reconciling

`master_debugger/types.py` and `master_debugger/orchestrator.py`'s `RiskLevel` unification (this branch's own v2.6.1 work, §11.6) required no merge action — the sibling branch's retrieved transcript never touched `RiskLevel` in either file, so there's no competing change to reconcile, only this branch's existing fix to preserve (which it was, untouched).

### 12.5 `input()` hang fixed — design decision made: mock stdin, not just a timeout

The last open item from earlier sessions (§11's Known Issues, carried through the v2.6.1/v2.5.2 reconciliation): `MasterDebuggerV5.debug()` hangs indefinitely on traced code that calls `input()`, since there's no interactive terminal in this sandboxed context and a blocking read waits forever. The handoff named three candidate fixes without picking one: timeout-wrap, mock stdin, or redirect from `/dev/null`.

**Decision: mock stdin (an in-memory empty buffer), not a timeout.** `python_debug/debug_report.py`'s `execute_with_debug()` already had an optional `timeout_seconds` parameter (SIGALRM-based) from an earlier session, but it was never given a default, so `Phase1RuntimeDebug.run()` never passed one — the mechanism existed but wasn't reachable from the actual hang path. A timeout alone would also have been the wrong primary fix even if wired up: it's Unix-only (SIGALRM doesn't exist on Windows), and it only resolves the hang after `timeout_seconds` elapses rather than immediately. Swapping `sys.stdin` for an empty `io.StringIO()` for the duration of `exec()` (restored in a `finally`, success or exception) makes any `input()` call fail instantly with `EOFError` — portable, immediate, and the `EOFError` gets captured by the existing exception-handling path exactly like any other crash, correctly attributed and reported, not silently swallowed. Added as `mock_stdin: bool = True` (opt-out available, default on — there is never a legitimate reason for traced code to block on real interactive input in this suite's actual usage context). The pre-existing `timeout_seconds` mechanism is kept as-is, documented as a secondary backstop for other hang categories (e.g. genuine infinite loops), not a substitute for the stdin fix.

No other call sites needed changes — `Phase1RuntimeDebug.run()` calls `execute_with_debug(code)` with defaults, so `mock_stdin=True` applies automatically through the existing `MasterDebuggerV5.debug()` → `Phase1RuntimeDebug.run()` → `execute_with_debug()` chain.

Verified at three levels, each with an external subprocess-level timeout as a safety net in case the fix itself was wrong (so a regression would fail loudly rather than hang the verification itself): direct `execute_with_debug()` call with an `input()`-calling snippet (returned instantly, `exception_info` correctly populated as `EOFError`); confirmed `sys.stdin` is restored to the caller's original object afterward, both on the crash path and the success path (a global mutation that outlives the call would be a worse bug than the one being fixed); confirmed the full `MasterDebuggerV5.debug()` → `Phase1RuntimeDebug` → `execute_with_debug()` chain completes instantly on real `input()`-calling code, with `phases_executed: [0, 1]` and a sensible `risk_level`, not a hang.

**Found, not fixed, out of scope for this task:** `DebugReport.finalize()` unconditionally sets `execution_complete = True` regardless of whether the run crashed (confirmed by direct testing: an `EOFError`-crashed run still shows `execution_complete: True`). This is a pre-existing, differently-named-field issue — the actual crash signal used by `to_dict()` and most of the reporting surface is `exception_info is not None`, which is correct and unaffected by this quirk, but `get_execution_summary()`'s top-level `"status"` field does rely on the (apparently mislabeled) `execution_complete` flag and would report `"completed"` even for a crashed run. Not touched this session — it predates the `input()` fix, is orthogonal to it, and fixing a field's semantics suite-wide deserves its own scoped pass rather than a drive-by change bundled into an unrelated bug fix.

5 new regression tests added to `src/python_debug/tests/test_execution_tracing.py`'s new `TestStdinMocking` class: instant-return-not-hang with correct `EOFError` attribution, crash correctly reported via `to_dict()`, stdin restored after both crash and success paths, opt-out (`mock_stdin=False`) leaves `sys.stdin` untouched, and non-`input()`-calling code is unaffected by the change (confirms no side effect on the common case).

Full suite after this fix: **327 passed, 46 skipped, 1 deselected, 0 failed** (322 + 5 new tests, zero regressions).

### 12.6 `SemgrepAnalyzer`/`LiefBinaryAnalyzer` test gap closed

The last item flagged twice (handoff's Test Strategy section, §12.3 of this file): neither had dedicated pytest coverage. Added `src/common/tests/test_semgrep_analyzer.py` and `src/cpp_debug/tests/test_lief_analyzer.py`, following the existing `@pytest.mark.skipif(not X_available(), ...)` pattern from `TestCBMCIntegration` in `test_symbolic_phase6.py`. Unconditional tests cover graceful degradation (tool not installed, no compiler, bad input never raises). Integration tests that actually invoke semgrep/lief are skipped in this sandbox (neither is installed here) but will run wherever they are. 9 new tests total (4 semgrep, 5 lief); full suite **332 passed, 57 skipped, 1 deselected, 0 failed**.

## §13. Six-archive feature-loss audit (2026-07-10, same session continued)

Max uploaded six old archives spanning this project's full lineage: `pyprover-v8-2.skill`, `pyprover_v11_2.skill`, `pyprover_skill__2_.zip` (unlabeled version, filenames match current bundled pyprover), `python-debug_skill.zip`, `debug-suite-v2_2.skill`, and `verification-debugging-suite-v1_1.skill` (the earliest full-suite snapshot, predating the `debug-suite` rename). Audited each for functionality present in the old archive but absent from the current `src/` tree — the same kind of audit `legacy_code/README.md` already existed to support, except this time with real source instead of `conversation_search` reconstructions.

### 13.1 Method

For the two full-suite snapshots (`debug-suite-v2_2`, `verification-debugging-suite-v1_1`) and the pyprover-only archive with filenames matching current modules (`pyprover_skill__2_`), used a mechanical sweep: for every `.py` file in the old archive with a same-named counterpart in current `src/`, diffed the set of top-level `def`/`class` names (`comm -23` on sorted name lists) to find anything in old-but-not-current. This catches dropped functions/classes without requiring a full line-by-line read of every file - appropriate for confirming *absence of regression* across a large, already-stable tree, as opposed to the deeper manual read needed to evaluate a *genuinely new* capability (which is what the other two archives turned out to contain).

For `pyprover-v8-2` and `pyprover_v11_2` - both from before PyProver had any adapter/template architecture in the current bundled version - the mechanical name-diff doesn't apply (there's no same-named current file to diff against). These got a full manual read, and for `pyprover_v11_2`, direct execution against real test cases in an isolated sandbox (`/home/claude/work/old-versions/pyprover_v11_2_test/`, not part of any packaged output).

### 13.2 Full-suite snapshots: verified clean, zero unintentional regressions

Swept every module (`code_orchestrator`, `common`, `troubleshooting`, `master_debugger`, `python_debug`, `pyprover`, `test_generator`, plus `cpp_debug`/`javascript_debug`/`rust_debug` in the v2.2 snapshot) against current. Total findings across both snapshots: exactly two, both already-known and intentional, not regressions:

- `common/pyprover_bridge.py::_create_placeholder_result` (present in v2.2, absent now) - its own docstring said "stand-in used until a real PyProver call is wired up." Confirmed current `pyprover_bridge.py` does call the real `pyprover.verify_contract()` now (line ~207) - this function's removal is exactly what its docstring predicted, not a loss.
- `master_debugger/orchestrator.py` and `types.py`'s local `RiskLevel` class (present in both old snapshots, absent now) - this is this branch's own v2.6.1 `RiskLevel` unification (§11.6), which intentionally removed three duplicate local `RiskLevel` enums in favor of importing one from `common.interop`. Already documented, not a new finding.

`pyprover_skill__2_.zip`'s `async_verifier.py`/`ffi_verifier.py`/`token_profiler.py`/`types_phase3.py` (filenames matching current `src/pyprover/`): zero dropped functions/classes, current is a confirmed strict superset (one addition found the other direction: a `strip_comment` helper added to `async_verifier.py` since this snapshot).

**Conclusion: current v2.7.0 is a verified strict superset of both full-suite snapshots and the matching-filename pyprover archive.** No merge action needed for any of these three archives.

### 13.3 `pyprover_v8_2_core_with_real_template_invariants.py`: real template logic, not integrated

`pyprover-v8-2.skill`'s `core.py` has a `TemplateBase` class hierarchy (`ACCUMULATOR`, `BINARY_SEARCH`, `MIN_MAX_LOOP`, `RECURSION`, `STATE_MACHINE`, `FILTER`, `SCAN`, `WHILE_LOOP`) where each template is a dataclass with a real `generate_invariant()` method producing an actual invariant expression (e.g. `MIN_MAX_LOOP` → `"{current_best} == min(arr[:i+1])"`). This is architecturally older than (and superseded by) the adapter-based system in `pyprover_v11_2`, but it has something v11.2 lacks: real per-template constraint content, versus v11.2's empty-stub template methods (§13.4). Requires manual parameterization (the caller supplies `current_best`, `arr_var`, etc. by hand) rather than automatic extraction from source. Archived to `legacy_code/pyprover_v8_2_core_with_real_template_invariants.py`; not integrated - see §13.5 for why combining this with v11.2's auto-detection isn't a same-session task.

### 13.4 `pyprover_v11_2.skill`: real source recovered, one bug found and fixed, one limitation documented

This directly supersedes `legacy_code/LANGUAGE_ADAPTER_GUIDE_recovered.md`, which was explicitly marked "NOT TESTED/VERIFIED" and reconstructed only from `conversation_search` summary snippets. Max's upload is the actual `pyprover_v11_2.skill` archive - real, complete source, not a lossy reconstruction. Removed the old reconstruction file; replaced with the real thing at `legacy_code/pyprover_v11_adapters/`.

Verified by running it (not just reading it), in an isolated sandbox with a real `ast`-based Python adapter, against three real Z3 test cases:

1. **Soundness bug, found and fixed.** `Z3Verifier.verify()` checked whether preconditions+postconditions+template-constraints were jointly *satisfiable* (`solver.check() == sat`) rather than whether the postcondition was *implied by* the preconditions (assert antecedent, negate postcondition, check UNSAT). Reproduced: `@requires("len(arr) > 0") @ensures("result < 0")` on a max-finder reported `verified: True` before the fix - a materially wrong postcondition passing as proven. Fixed in `legacy_code/pyprover_v11_adapters/verifier_SOUNDNESS_FIXED.py` using the same implication-check pattern this project's own `contract_simplifier.py`/`loop_verifier.py` already use correctly (and the same bare-identifier Bool/Int guard fixed earlier the same session, ported here since this verifier has the identical exposure via its own `eval()`-based expression parser). Re-verified: the false-positive case now correctly reports `verified: False` with a counterexample; a genuinely-provable case still reports `verified: True`; a bare-identifier `@ensures` clause no longer crashes.
2. **Architectural limitation, not fixed, documented.** `_accumulator_constraints()`, `_binary_search_constraints()`, `_min_max_constraints()` are all empty-list stubs - the "10 verification templates" this system advertises contribute zero actual proof content, even after the soundness fix. `template_type` is classification metadata only; the verifier can only check logical consistency between stated `@requires`/`@ensures` clauses as bare formulas, with no model of what the code's loop body actually computes. This is a materially weaker guarantee than this project's own already-shipped `pyprover/loop_verifier.py` (real Hoare-logic INIT/PRESERVATION obligations tied to actual loop AST structure).

Full detail, including the exact reproduction code and the `eval()`-restriction note, is in `legacy_code/pyprover_v11_adapters/FINDINGS.md`.

**What this means for a future integration:** the genuinely valuable, non-duplicated asset in this archive is the **adapter/parsing layer** (`adapters/python_adapter.py`'s real `ast`-based `@requires`/`@ensures`/`@assume` extraction, plus JS/TS/NASM/FASM/WASM equivalents at varying levels of real-vs-regex parsing per adapter) - not the verification core, which after this session's fix is sound but shallow, and which this project's own `loop_verifier.py` already exceeds for the templates both cover. A real integration should port the adapters' `extract_contracts()` output into this project's existing (stronger) verification engine, and - per §13.3 - could draw on v8.2's `generate_invariant()` pattern to give the currently-stub template methods real content, though that still needs a third piece (binding extraction: which variable is `current_best`, which is `arr_var`) that exists in neither archive as uploaded.

### 13.5 Why this wasn't integrated into `src/pyprover/` this session

Scope, stated plainly rather than silently thinned: a real integration is 6 languages' worth of adapter code, each needing conversion from this archive's standalone `Contract`/`VerificationResult` types to this project's `common.interop` types (the same conversion `pyprover_bridge.py::_adapt_local_result()` already does for the bundled `ContractVerifier`), rewired onto the existing verification engine instead of the weaker one bundled here, plus tests per language. That's a multi-session scope on its own (the original v11.2 build itself drew on at least 3 separate source chats per the superseded `legacy_code` index). This session did the higher-leverage work first: recovered the real source (replacing a marked-untested reconstruction), found and fixed a real soundness bug via actual execution rather than a read-through, and identified precisely which part of the archive is worth porting and which part shouldn't be (the verification core, in its bundled form). That's the right foundation for a focused future integration session - starting from verified, corrected code and a clear scope instead of an untested reconstruction and an open question.

### 13.6 `python-debug_skill.zip`: one ambiguous finding, not merged

`debug_report.py` and `bug_patterns.py`: zero dropped functions, current is a confirmed superset (current `debug_report.py` includes this session's own `mock_stdin` fix, §12.5). `benchmark_debug.py` and `analyze_timeline.py`: byte-identical to current.

`conftest.py` differs substantially, but not as a clean superset/subset - it's a genuine divergence. The old version has richer, more specific test infrastructure: a `DebugAssertions` helper class (`assert_traces_correctly`, `assert_detects_pattern`, `assert_has_aliases`, `assert_execution_time`), more granular named scenario fixtures (`simple_code_scenario`, `complex_code_scenario`, `aliasing_scenario`, `crash_scenario`, `fixture_injection_scenario`), a `pattern_detection_timer` fixture, and a `pytest_runtest_makereport` performance-regression hook (stubbed, `pass`). Current `conftest.py` consolidated these into fewer, more generic fixtures (`execution_timer`, `memory_tracker`, a `code_scenarios` dict) with centralized marker registration.

**Not merged - this is ambiguous, not a clear loss.** Unlike the pyprover adapter case (a standalone capability that simply stopped existing), this looks like a deliberate consolidation: current tests already use the newer, simpler fixtures, and forcibly reintroducing the old named fixtures/helpers risks fixture-name collisions or unused dead code rather than restoring something broken. Flagging as a real difference worth a human call, not a merge action: if Max wants the more granular scenario fixtures or the `DebugAssertions` helper class back, that's a quick, low-risk follow-up (they're self-contained additions, not a replacement of anything current tests rely on) - just not one to make unilaterally without knowing whether the consolidation was deliberate.

### 13.7 Session test suite status

No net-new tests from this audit itself (it was read/diff/execute-in-isolation work, not integration work) - full suite remains at the count from §12.6's end: 332 passed, 57 skipped, 1 deselected, 0 failed.

## §14. The real sibling v2.5.2 archive, and a stub replaced with real code (2026-07-10, v2.8.0)

Max uploaded the actual `debug-suite.skill` v2.5.2 archive - the real sibling branch this project reconciled with in §12.1 using only `conversation_search` transcripts, before the real file was available.

### 14.1 Verifying the earlier reconciliation

Confirmed `SKILL.md`'s `metadata.version: 2.5.2` directly (not inferred). Its own `CHANGELOG.md` is stale relative to its own version (last entry is `[2.2.5]`, seven versions behind `2.5.2`) - a documentation gap in the sibling branch itself, not something to fix here (not this project's file).

Ran the same function/class-presence sweep used for the six-archive audit (§13.1's method) across every file in the real archive against this package. Three of §12.1's four reconciled items are byte-for-byte identical to the real thing: `master_debugger/__init__.py`, `pyprover_bridge.py`'s `_map_language_type`, `requirements.txt`. High confidence the `conversation_search`-based reconstruction was accurate, not just plausible.

### 14.2 The real finding: `contract_verifier.py` was a non-functional stub, and existing tests never caught it

The sweep flagged `src/pyprover/contract_verifier.py` as having 5 functions in the sibling not present here (`_check_implied`, `_check_satisfiable`, `_clause_to_z3`, `_expr_to_z3`, `_is_z3_bool`). Expected, per §12.1's own finding: this branch's `contract_verifier.py` is a 154-line stub, architecturally different from the sibling's real implementation, which is why the earlier session's bare-identifier fix went into `contract_simplifier.py` instead.

Read the real file this time (not just the `conversation_search` snippets that surfaced `_check_satisfiable` for the earlier session's contract_simplifier.py fix). It's a complete, working `ContractVerifier`: `ast`-based (no `eval()`) comment-annotation parsing, real precondition satisfiability, postcondition *validity* via implication-checking for clauses that don't reference the return value, satisfiability-only (by explicit documented design) for clauses that do, invariant satisfiability, its own input-size hardening, its own `_is_z3_bool` guard.

This is exactly the capability §13.4's `FINDINGS.md` said was missing: *"the decorator-based `@requires`/`@ensures` contract system with real Z3 solving... isn't part of this branch's live `src/` tree."* That claim was accurate for the *decorator*-based system (`pyprover_v11_adapters`, still not integrated, see §13.4) - but this is a different, simpler *comment*-annotation-based system, and it turns out this project's own `pyprover/__init__.py` and `pyprover_bridge.py` were already wired up expecting exactly this, the whole time. `pyprover/__init__.py`'s `verify_contract()` calls `ContractVerifier().verify_contract(code)` and has said `"""PyProver v14.1"""` since before this session - the plumbing expected a real verifier; only the verifier itself was a stub.

**More significant than the missing capability itself: this session's own existing test suite never caught it.** `TestContractVerification`, `TestVerificationEdgeCases`, `TestContractParsing` all call `ContractVerifier().verify_contract(code)` and assert things like `assert result.get('verified') is True or result is not None` - true for any dict, vacuously, regardless of whether real verification happened. Confirmed by direct testing before replacing the stub: `# Pre: x > 0` / `# Post: x > 100` (a precondition that provably does not imply its postcondition - counterexample `x = 1`) reported `verified: True` against the stub. The tests were green the entire time this project's roadmap correctly documented the stub as a known limitation - green tests and an honestly-disclosed limitation coexisted because the tests never actually exercised the limitation.

### 14.3 Fix: replaced the stub, re-verified with real proof/counterexample cases, confirmed bidirectional (not one-way)

Replaced `src/pyprover/contract_verifier.py` wholesale with the sibling's real implementation. Re-verified with cases designed to distinguish real verification from the stub's near-universal `verified: True`:

- `# Pre: x > 0` / `# Post: x > 100` → now correctly `verified: False`, counterexample `x = 1`.
- `# Pre: x > 100` / `# Post: x > 0` (genuinely implied) → `verified: True`, "implied by preconditions."
- End-to-end through `PyProverBridge.verify()`: the false-positive case now correctly classifies as `RiskLevel.CRITICAL` with the real counterexample surfaced in the summary text - confirms the `_adapt_local_result` conversion layer (already written expecting a real verifier's output shape) works correctly with actual real output, not just the stub's.
- Full suite: 332 passed, 57 skipped, 1 deselected, 0 failed - same count as before the swap (this was a same-file replacement, not new tests), but the existing `ContractVerifier` test classes are now meaningfully exercising real behavior instead of passing vacuously.

**Confirmed bidirectional, not a one-way "sibling is strictly better" merge:** diffed sibling's `contract_simplifier.py` against this branch's - sibling does *not* have this session's earlier bare-identifier fix (§12.1's contract_simplifier.py `_is_z3_bool` guard). That fix is preserved; only `contract_verifier.py` was replaced. Each branch had a real fix the other lacked, in different files, for the same underlying bug class - consistent with §12.1's original finding that the two branches diverged architecturally rather than one simply being ahead of the other.

### 14.4 Updated docs

`SKILL.md`'s PyProver capability line now says what `ContractVerifier` actually does (implication-checking, not just satisfiability) instead of the older, vaguer "Z3 satisfiability" phrasing that was technically accurate for the stub but undersold what the plumbing was always designed for.

## §15. `ContractSimplifier` documentation clarity + pydebug merge re-verification (2026-07-10)

### 15.1 `ContractSimplifier` was ambiguously documented, inviting a real misreading

Max described `ContractSimplifier` as something that "checks using contracts and a mathematical proof if the code can be simplified and have the same result." Checked the actual implementation before writing anything: `ContractSimplifier.simplify(requires: List[str], ensures: List[str])` takes only clause strings - it never receives or inspects a function body. What it proves is narrower than the description: whether a clause in a contract *specification* is logically redundant given the *other clauses in that same spec* (implied by them, or a tautology) - not whether two versions of *code* produce the same result. No code-to-code equivalence checking exists anywhere in this suite, bundled or in `legacy_code/`.

The previous SKILL.md wording ("Iterative Z3 implication checking removes redundant clauses") was technically accurate but didn't rule out the code-equivalence reading - "simplifier" is a genuinely ambiguous name for what this does. Rewrote three places to close the gap: the terse bullet in the components list, a new prominent "what it actually does / what it does NOT do" paragraph in the PyProver capability section (explicitly naming the code-equivalence reading as the wrong one, since without an explicit example of the wrong interpretation, it's easy for a future reader to make the same reasonable guess), and the module docstring in `contract_simplifier.py` itself (read first when the file is opened directly, independent of SKILL.md).

Not a code change - `ContractSimplifier`'s actual behavior is unchanged and was already correctly implemented for what it does do (§12.1 confirmed this earlier in the session). This was purely a documentation-precision fix to prevent a future Claude instance (or Max) from expecting or claiming a capability that doesn't exist.

### 15.2 "pydebug" re-verified: confirmed properly merged, including a bug-fix pass I hadn't previously checked

`conversation_search` for "pydebug" (confirmed via search results to be Max's own shorthand for `python-debug`, not a separate skill) surfaced something the earlier §13.6 audit hadn't accounted for: a dedicated fix session (chat `1492eee2-fa60-4c1c-97c3-a4b7ff7eb767`) that found and fixed 6 real bugs in `debug_report.py`, taking its test suite from 12/19 to 19/19 passing. §13.6's earlier check was a function/class-*name* diff, which can't detect a *behavioral* regression where the function still exists but a bug in its body was never fixed - a meaningfully different and stronger claim needed direct testing, not name comparison.

Verified each of the 6 documented bugs directly against this package's actual `debug_report.py`, not by re-reading the old fix session's claims:

1. **`exception_info` API mismatch (Dict vs Tuple)** - confirmed `dict` type in this package.
2. **`final_state` serialization losing types on non-JSON-safe values** - tested with a class with a deliberately-broken `__repr__` and a `set` (not natively JSON-serializable); both handled gracefully (`to_json()` succeeds, no crash).
3/4. **Aliasing/mutation tracking incomplete (root cause: `sys.settrace`'s "line" event fires *before* the line executes, so same-line assignments were missing from `variables_after`)** - tested `x = [1,2,3]; y = x; z = x; x.append(4); y.append(5)`: all three variables correctly identified as aliases of the same object, all mutations correctly reflected in `final_state`.
5. **`bug_patterns.py` API incompatibility with the fixed `exception_info` format** - tested a division-by-zero case through the full `BugPatternDetector` pipeline: `DIVISION_BY_ZERO` correctly detected.
6. **Test suite bugs** - not independently checkable (was about the *old* standalone test file's own assertions, not this package's), but this package's own `python_debug` test suite (33 tests, a superset of the 19 from that session) passes in full: 33/33.

**Conclusion: pydebug is confirmed properly merged, this specific bug-fix pass included.** No corrective action needed - this section exists to record that the deeper, behavioral check was done and passed, not just the shallower name-presence check from §13.6.

## §16. `EquivalenceVerifier` built (2026-07-10, v2.9.0) — the capability §15.1 said didn't exist

### 16.1 Scope decision, stated before writing code

Max asked for "a contract verifier like system to extrapolate the simplest equivalent code from more verbose code." Read literally and fully generally, this is program synthesis with an optimality claim ("the simplest") - undecidable for arbitrary Turing-complete code (two programs' equivalence is Rice's-theorem territory; there's no algorithm that decides it for every pair). Said so directly rather than quietly building something narrower and calling it what was asked for.

Built the honest, tractable version instead, stated as two separable pieces: (1) a **verifier** - given two code snippets, prove them equivalent or find a counterexample, directly analogous to `ContractVerifier`'s architecture and reusing its expression-translation layer; (2) a **simplifier** - not synthesis/search, but handing the verifier's own symbolic representation of a function to Z3's sound term-rewriter, which is a real, algebraic reduction, not a guess. Explicitly did not attempt open-ended rewrite search or multi-candidate synthesis - `propose_redundant_branch_removal()` is one hand-written pattern, chosen because it's simple enough to verify by inspection that the pattern-match logic itself is correct, not because it's the start of a general engine.

### 16.2 Architecture: reuse, not reimplementation

`equivalence_verifier.py` imports `_expr_to_z3`/`_OP_MAP` directly from `contract_verifier.py` rather than duplicating expression-to-Z3 translation a third time (contract_verifier.py, contract_simplifier.py, and now this module all need it - contract_simplifier.py has its own copy from before this session; a future cleanup could consolidate all three onto one shared translator, not done here to avoid an unrelated refactor riding along with a new feature). The new capability is entirely in the statement/control-flow layer on top: tracking variable assignment across statements, combining `if`/`else` branches, and bounded loop unrolling - none of which existed anywhere in this suite before.

### 16.3 Two real bugs found while building, not just at the end

Per this project's established practice (verify by running, not by reading), tested every piece incrementally before writing the formal test suite - and both bugs below were caught this way, before they could hide behind a passing-by-coincidence test the way §15.2's audit found in `ContractVerifier`'s old stub.

**Bug 1 - the control-flow design was wrong on the first pass.** The initial `if`/`else` handling required both branches to return, or neither to - anything else (`if cond: return X`, followed by more code) was rejected as "ambiguous." That's not actually ambiguous; it's the single most common branching shape in real code (early return), and rejecting it would have made the tool nearly useless for anything past toy examples. Caught by testing a deliberately ordinary example (`if x > 10: result = 100` / `result += 1` / `return result`) before assuming the design was right. Rewrote `_exec_stmts` around an explicit `("return", value)` / `("fallthrough", env)` flow representation: when exactly one branch returns and the other falls through, the falling-through branch's flow continues into the remaining statements, and the combination is only accepted if that remainder itself definitely returns - otherwise it's correctly rejected as "does not return on every path," a real error rather than a tooling limitation. Both directions (then-returns/else-falls-through and its mirror) have regression tests.

**Bug 2 - unsupported constructs could crash instead of degrading.** `contract_verifier._expr_to_z3` (the reused leaf-expression translator) raises a raw `NotImplementedError` for anything it doesn't handle - function calls, attribute access. The new module's public functions caught `UnsupportedConstructError` (this module's own exception type) but not the raw `NotImplementedError` bubbling up from the reused code, so a recursive function or `x.attr` access would crash instead of returning `status="unsupported"`. Fixed with `_expr_to_z3_safe()`, a thin wrapper applied at every call site that converts the exception type. Separately (not the same bug, found by the same "test the obvious next case" habit): expressions using a bare boolean variable directly with `and`/`or`/`not` (e.g. `not a`) hit a genuine *inherited* limitation - the reused translator always seeds an unbound name as a Z3 `Int`, so `Not()` on it is a sort mismatch. This isn't a bug introduced here; it's `contract_verifier.py`'s own existing scope boundary (consistent with SKILL.md's long-standing "integer arithmetic clauses only" note for the same translator), surfaced now because this module is the first caller to hit it with genuinely boolean free variables. Caught the raw `Z3Exception` at the three call sites that could produce it and reported it with a specific, actionable workaround (use an Int-typed comparison) rather than a bare stack trace.

### 16.4 Verification method

Every piece tested by direct execution before being declared working, consistent with this project's standing practice: expression equivalence (algebraically-equal case, unequal case with a real counterexample, and specifically an unequal-by-a-constant case with no free variable in the model, which turned out to need its own formatting fix); function equivalence across nested/nested-redundant branches, the early-return pattern, a wrong "simplification" correctly rejected with a counterexample, bounded-loop accumulator-vs-closed-form (Gauss sum, `range(10)` unrolled) both correctly proven and correctly caught when wrong, and a loop deliberately exceeding `max_unroll` correctly rejected rather than silently truncated; `simplify_function()` on the same redundant-branch example, cross-checked against `verify_function_equivalence()` independently (not just trusting `simplify_function`'s own Z3 usage) to confirm the two entry points agree; the rewrite-pattern proposer on both a matching case (proposes and verifies) and a non-matching case (correctly returns nothing). 28 tests in the module's own file plus 4 through `PyProverBridge`, all passing; full suite 364/364, zero regressions from the 332 baseline.

### 16.5 What's still out of scope, on purpose

List/dict/string operations, recursion, generators, unbounded loops, multiple return values, and function calls other than the arithmetic/boolean operators `contract_verifier.py` already handles. Bare boolean variables need an Int-typed comparison as a workaround (§16.3). None of these are silently mishandled - every one raises `UnsupportedConstructError` or reports `status="unsupported"` with a specific reason. Extending the supported subset (e.g. adding string operations, or invariant-based reasoning for unbounded loops instead of bounded unrolling) is real future work, not attempted this session - the module docstring's own scope statement is the honest boundary of what got built, not an aspirational one.

## §17. Two real stubs found via body-diff; a merge-methodology gap disclosed (2026-07-10, v2.9.1)

### 17.1 How this was found

Re-read the sibling v2.5.2 branch's own conversation summary (chat `3abe64d4-9daa-44e5-acc8-5e4e6cda9f6b`, first surfaced in §12.1 but not re-read in full at the time) while searching for other chats to link for Max. It mentions "a stub-elimination pass that found and replaced three real stubs... `ContractVerifier.verify_contract()`... `RustDebugger.phase_2_formal()`... and `MasterDebugger.classify_risk()`." §14 already merged the first of these (`ContractVerifier`). The other two were never checked - §14's sweep method (comparing which function/class *names* exist in each branch) can't see a same-named function with a different, worse body. Ran a plain `diff` on every file that exists in both branches (not a name-presence check - the actual file contents) and found exactly these two, confirmed by direct execution: `classify_risk("eval(x)")` returned the identical `{"risk_level": "medium", "score": 0.5}` as `classify_risk("x = 1")` before the fix (a hardcoded stub, not degraded-but-real classification), and `phase_2_formal()` returned `None` unconditionally regardless of input before its fix.

### 17.2 What got merged, and what didn't (this wasn't a wholesale swap)

`classify_risk()`: took the sibling's real implementation wholesale - four-tier pattern-based classification (CRITICAL/HIGH/MEDIUM/LOW), verified to produce genuinely different scores for genuinely different inputs.

`phase_2_formal()`: **surgical merge, not a file replacement.** The full diff of `rust_debug/phases.py` showed this branch is actually *ahead* of the sibling elsewhere in the same file - `phase_1_runtime`'s tool-availability-aware confidence scoring and honest degradation messaging (distinguishing "no issues found because the code is clean" from "no issues found because rustc/clippy never ran") is this branch's own work, absent from the sibling. Replaced only the `phase_2_formal` method body, leaving the rest of the file - including the parts where this branch is ahead - untouched. Confirms §14.1's original finding held here too: the two branches diverged in both directions on different files, not one being a strict superset of the other.

Also swept `c_debug/*.py` and `cpp_debug/*.py` for the same class of hidden stub via full body-diff (not just name-presence) while doing this pass, since those were flagged as "differ" back in §14's initial file-list sweep but never individually inspected. Confirmed clean: every difference in those files is this branch being ahead (valgrind integration, cppcheck, lief, the CBMC 6.x flag-name fix) - real content on this branch's side, nothing missing.

### 17.3 The disclosure that matters more than the two fixes themselves

§13's six-archive audit and §14's sibling reconciliation both used exactly the name-presence-only method that just missed two real stubs here. Manually body-diffing `c_debug`/`cpp_debug`/`master_debugger/phases.py` this session (§17.2) came back clean, which is a good sign for §13's other six archives by the same logic - but "the one file I manually checked was fine" is a materially weaker claim than "verified strict superset," which is the phrase §13.2 actually used. **Not going back to re-audit all six archives from §13 with a full body-diff this session** - that's real, bounded, separately-scoped work (six archives × every shared file, actually reading bodies not just names), and doing it properly deserves its own pass rather than a rushed pass appended here. Flagging this precisely so a future session (or Max) knows exactly what "verified" meant at the time §13 was written, and what it would take to strengthen that claim.

### 17.4 Test coverage added

7 new tests: `TestMasterDebuggerV6ClassifyRisk` (4 tests) covering the same-score-for-everything regression specifically (`test_different_inputs_give_different_scores`, the test that would have caught this stub immediately had it existed before). `rust_debug` had zero test coverage before this session - created `src/rust_debug/tests/` with 3 tests scoped specifically to `phase_2_formal()`; broader `rust_debug` coverage (phase_0/phase_1/phase_3, `RustDebugger.debug()` end-to-end) is a separate, larger, pre-existing gap not addressed here. Full suite: 371 passed, 57 skipped, 1 deselected, 0 failed.

## §18. Quantifier support and ghost state tracking merged; loop_verifier integration deliberately deferred (2026-07-10, v2.9.2 / pyprover v14.2)

### 18.1 What this closes from §1/§2

§1's branch table lists quantifiers as part of Branch A (`forall` referenced in the v7.0 proof-export line) and ghost state as part of an unversioned phase1-3 build that predates all three branches in that table (not previously catalogued here — found during a separate version-comparison pass, not in the original conversation-history search that produced §1). Neither ever made it into Branch C (`src/pyprover/`, the branch actually merged into this suite). Checked directly before starting, the same way §1 insists on: `grep -rl "forall\|ghost\|quantifier" src/pyprover/*.py` returned only `types_phase3.py`'s `FFIContract.to_z3_constraint()`, and that occurrence is a hardcoded string literal (`"(forall (p) (not (null p)))"`) baked into an f-string, never parsed or passed to Z3 — the same "looks like a real signal, ignores the input" failure mode §17's `classify_risk()` stub was.

**What Branch A's own v7.0 had for quantifiers, checked directly rather than assumed:** nothing real either — `pyprover-v7-0-skill`'s `references/prover_extended_v7_0.py` has no `ForAll`/`Exists`/quantifier handling at all despite the branch table listing "forall" as part of its proof-export work; that was v13.1's own `ConstraintGenerator.parse_contract_expression()` (Branch B, not A) that matched `all(...)`/`any(...)` syntax by regex and discarded the quantified condition, asserting only a structural stand-in (`length >= 0`) instead of the real statement. So this is not a restoration of a working prior implementation — every prior version's quantifier "support" was either a hardcoded string template or a regex match that threw the condition away. What was built this session is the first real one across any branch: `check_quantifier()` hands an actual `z3.ForAll`/`z3.Exists` (or, for small literal bounds, a bounded-unroll conjunction/disjunction — same principle §16's `EquivalenceVerifier` already established for `for x in range(N)` loops) to the solver and reports a genuine counterexample on violation.

**Ghost state**, similarly: the unversioned phase1-3 build's `GhostStateTracker` only ever appended free-text strings to a list and returned them unmodified — no Z3 involvement, so "tracking" meant storage, not checking. `ghost_state.py`'s `GhostStateTracker.check_consistency()` now actually asserts declared ghost variables and their updates into a Z3 solver alongside real-variable constraints and checks satisfiability — a real contradiction (e.g. a ghost declared equal to a variable that a precondition constrains to be negative, alongside a non-negativity requirement on the ghost) is now detected as UNSAT, not silently accepted. Two bugs were found and fixed by this module's own tests before it shipped, not after: an early-return that reported "verified" without checking updates when no declarations were present, and a docstring overclaiming "jointly satisfiable with real-variable constraints" when no such constraints were actually being passed in anywhere in the call chain (fixed by adding an explicit `real_var_constraints` parameter and reporting which mode — weak self-consistency vs. the stronger claim — actually ran, in `detail`).

### 18.2 What was NOT done: `loop_verifier.py` INIT/PRESERVATION quantifier integration

`quantifiers.py` was deliberately **not** wired into `loop_verifier.py`'s `verify_loop_invariant()`, even though loop invariants are the single most natural place to want a quantified condition (e.g. "`forall j < i: arr[j] is sorted`" as a sorting-loop invariant). Checked what currently happens: `_parse_invariant_expr()` calls the file-local `_expr_to_z3()`, which raises `NotImplementedError` on the `ast.Call` node a quantifier's `all(...)`/`any(...)` syntax produces, and `verify_loop_invariant()` already catches `NotImplementedError` and reports `skipped=True` with a reason — confirmed directly (`skipped: True | reason: Unsupported expression: Unsupported node type: Call`). So today a quantified loop invariant degrades safely to an honest skip, never a false "verified".

**Why this wasn't just wired up the same way `contract_verifier.py` was this session:** `contract_verifier.py`'s clauses are checked once, independent of any notion of "before vs. after one loop iteration" — `check_quantifier()`'s job there is exactly "is this quantified statement true," full stop, which is what a `# Post:` clause needs. `loop_verifier.py`'s INIT/PRESERVATION model is different in kind: PRESERVATION needs to show the invariant holds *again* after advancing the loop variable by one step, for an *arbitrary* iteration — i.e., it needs induction, not a single evaluation. Naively reusing `check_quantifier()` for PRESERVATION (evaluate the quantifier once at some Z3-symbolic state) would silently prove something weaker than what "PRESERVATION verified" is supposed to mean, and would very likely get reported as a real verification the way the rest of this suite's `LoopVerificationResult.verified` field is currently trusted elsewhere — exactly the "looks complete, isn't" failure mode this whole roadmap file exists to flag, not one to add to it. Given the session's remaining time, shipping an honest skip beat shipping a plausible-looking-but-unsound integration.

**Roadmap item — what real PRESERVATION-with-quantifiers would need**, for a future session:

| Sub-task | What it requires |
|---|---|
| Symbolic step model | Represent "one loop iteration" as a state transition (not just `var == var + 1` as the current scalar PRESERVATION check does at line ~294 of `loop_verifier.py`) that also updates any array/collection the quantifier ranges over |
| Quantified INIT | Reuse `check_quantifier()` as-is here — INIT genuinely is a single-state check ("is `I` satisfiable at entry"), so this part of the existing plan already composes correctly with no new work |
| Quantified PRESERVATION | Needs `z3.ForAll` over *both* the quantifier's own bound variable and the implicit "which iteration" state, or an explicit induction lemma structure — this is a materially harder Z3 encoding than anything currently in `loop_verifier.py`, closer to what a real Hoare-logic verifier (Dafny/Why3-class tooling) does than a `+1` scalar check |
| Test cases | At minimum: a real sorting-loop invariant (`forall j < i: arr[j] <= arr[j+1]`) proven inductively, plus a deliberately-broken variant confirmed to be caught (mirroring how `test_forall_violated_has_real_counterexample` proves the non-loop version isn't just always returning verified) |
| Estimated size | Not smaller than `equivalence_verifier.py` (§16, ~400 LOC + 32 tests) given the added state-transition modeling; likely larger |

Not attempted this session; flagged here rather than left implied-covered by the `contract_verifier.py` wiring that was actually done.

### 18.3 Test coverage added

28 new tests: `test_quantifiers.py` (14 — parsing, bounded-unroll verify/violate with real counterexamples, native-Z3 strategy for symbolic and large bounds, the z3-unavailable boundary), `test_ghost_state.py` (11 — extraction, self-consistency, the stronger real-constraints mode, a genuine UNSAT contradiction actually detected, the undeclared-ghost-reference and unparseable-expression boundaries), plus 3 integration tests in `test_verification.py`'s new `TestQuantifiedContracts` class exercising the `# Post: all(...)`/`any(...)` path through `ContractVerifier.verify_contract()` end-to-end. Observed locally in this environment: 350 passed, 57 skipped, 1 deselected, 0 failed (322 + 28, zero regressions) — noting per §17.3's own standard that this session's baseline (322 passed) was directly measured here rather than assumed from §17.4's "371 passed," since the two numbers disagree and re-deriving why was out of scope for this pass; likely environment/optional-tool-availability difference, not a regression, but stated as an open discrepancy rather than silently reconciled.

## §19. `len()`/`abs()`/`min()`/`max()` and string predicates — real Call-node support (2026-07-10, v2.9.3 / pyprover v14.3)

### 19.1 How this was found

Not a version-comparison finding — direct testing. After §18 shipped, went looking for other old-version features worth merging and, before assuming the answer was "port more of v6.1/v7.0," ran a quick probe of ordinary contract patterns against the fork as it stood: `len(arr) > 0`, `abs(result) >= 0`, `result == max(a, b)`, `s == "hello"`. All four came back `"non-arithmetic — skipped"`. That phrase is the same one a genuinely-malformed clause gets, so nothing about the output looks alarming — it reads as "this particular clause happened not to parse," not "an entire category of common contract syntax is invisible to the verifier." Checked why: none of the three `_expr_to_z3()` copies (`contract_verifier.py`, `loop_verifier.py`, `contract_simplifier.py`) has an `ast.Call` branch at all — every one falls through to `raise NotImplementedError(f"Unsupported node type: ...")`, caught upstream and reported as a skip.

**Why this wasn't caught by §1-§17's audits:** those audits (rightly) focused on cross-branch feature comparison — what Branch B/A had that Branch C (this fork) doesn't. This gap is different in kind: it's not a feature Branch C is missing relative to some other branch, it's a category of ordinary Python syntax that none of the three branches' `_expr_to_z3`-style translators ever handled, because `ast.Call` support was never part of any of their designs. A cross-branch diff would never have surfaced it; only exercising the actual verifier against realistic input would, and hadn't been done systematically before this.

### 19.2 What connects to the old versions, and what doesn't

PyProver v6.1/v7.0's `StringWorkAround` (`encode_string`/`decode_string`/`str_length`/`str_equals`/`str_contains`/`str_starts_with`/`str_ends_with`) is the direct precedent for the string-predicate half of this. But it was ported as a *capability*, not as an *implementation* — v6.1/v7.0 hand-encoded strings into scaled integers because those versions weren't using Z3's real string theory (`z3.SeqSort`/`z3.String`/`z3.Length`/`z3.Contains`/`z3.PrefixOf`/`z3.SuffixOf`), which z3-solver has had natively for years. Reimplementing the old integer-encoding workaround here would have been strictly worse than what's now shipped: the real theory is exact where the old workaround was an approximation, and it's less code. This is "restore the old feature, built correctly" rather than "port the old code," and that distinction matters for anyone reading the diff and expecting to find `encode_string`/`decode_string` ported verbatim — they won't, on purpose.

`len()`/`abs()`/`min()`/`max()` have no direct precedent in any of the three catalogued branches (§1's table) or the unversioned phase1-3 build — they're not a restored old feature at all, just a gap found by testing. Documented here anyway since the person asking for "other old-version features" should know not everything merged this session came from an old version.

### 19.3 What's still deferred: float precision

v6.1/v7.0's `FloatWorkAround` (`scale_float`/`unscale_int`/`approx_equal`/`approx_greater`/`approx_less`) was **not** ported, and unlike the string case, this isn't a "do it properly instead" swap-out — it's a real remaining gap. Z3 has native `Real`/`FP` sorts that would make the old int-scaling workaround just as obsolete as the string one, but wiring a second alternate sort through three call sites that all currently assume every bare name defaults to `z3.Int` needs the same kind of type-inference pre-pass `z3_builtins.infer_string_names()` does for strings — built for a different sort, with different implications for comparison operators (`Real` supports `<`/`<=` natively the way `Int` does, but "approximately equal" reasoning of the kind the old `approx_equal`/`approx_greater`/`approx_less` functions provided has no single obvious Z3 native equivalent — it needs an explicit epsilon parameter, which the old API also had and which the current `_expr_to_z3` signature has no natural place for). Estimated smaller than §18.2's loop_verifier item (no induction needed, just a new sort and an epsilon-aware comparison scheme) but not attempted this session.

### 19.4 Test coverage added

30 new tests: `test_z3_builtins.py` (21) and `TestBuiltinFunctionContracts` in `test_verification.py` (9). Full detail in CHANGELOG.md's v2.9.3 entry. Observed locally: 380 passed, 57 skipped, 1 deselected, 0 failed (350 + 30, zero regressions).

## §20. Two severe synthesis bugs in the orchestrator's own aggregation; closes §5's conflict-resolution item as a bug fix, not a feature port (2026-07-10, v2.9.4)

### 20.1 How this was found

Went looking for the next item on this list worth merging for bug-catching, and §5's "MISSING — conceptual model, not code" entry (master-debugger v3.0's three-stream blind-spot model with explicit conflict resolution) was the clearest remaining candidate: high value, flagged low effort. Before writing new conflict-resolution code, tested whether the existing orchestrator could even reach a state where two streams' findings would be compared — constructed a minimal case (a function with a real `NameError` in its body, called once, alongside a trivially-true formal contract) and ran it through `MasterDebugger.debug_comprehensive()` directly. It returned `overall_health="✅ VERIFIED"`, `risk_level=RiskLevel.LOW`. That result is wrong on its face (the function crashes on every call), and tracing why turned up two independent, compounding bugs, not one missing feature:

1. `python_debug/bug_patterns.py`'s exception-driven dispatch only had cases for four exception types. Confirmed via `report.exception_info` that the `NameError` was captured correctly by the tracer — `Phase1RuntimeDebug.run()` just never turned it into a pattern, because none of `BugPatternDetector`'s detectors handled that exception class.
2. `master_debugger/orchestrator.py`'s final synthesis block checked `if report.issues_found:` to decide whether to report `"✅ VERIFIED"` — but `report.issues_found` structurally could not contain static or runtime findings; only async-concurrency findings from `_phase_2_async` were ever appended to it. Static/runtime findings were counted into local `int` variables (`static_issues`, `runtime_issues`) used only for a `total_issues` number that the `"✅ VERIFIED"` branch never actually consulted.

### 20.2 Why this is filed as closing §5, not as a separate item

§5 asked for "an explicit synthesis/conflict-resolution phase... when a static check and a runtime trace disagree," modeled on master-debugger v3.0's blind-spot documentation. What actually shipped is that behavior, but arrived at differently than porting v3.0's content would have: v3.0 (and the newly-found v4, see §20.4) are Claude-facing *methodology documents* — SKILL.md instructions telling a Claude session how to manually run three parallel investigations and reconcile them. `orchestrator.py` is real Python code with actual `Issue`/`UnifiedDebugReport` dataclasses. There was no v3.0/v4 *code* to port for this, because those versions never had code — restoring the concept here meant fixing the orchestrator's own two real bugs (§20.1) until it was structurally capable of disagreeing with itself, then adding an explicit `CONFLICT` branch to the four-way synthesis (clean-verified / conflict-vacuous / conflict-genuine / issues-no-formal-result) once that was possible. Same "restore the capability, not necessarily the old artifact" pattern as §19.2's string predicates, for a different reason: there, real Z3 theory made the old artifact worse than the alternative; here, the old artifact was never code to begin with.

### 20.3 The vacuous-verified nuance, noted not fixed

`ContractVerifier.verify_contract()` returns `verified: True` for code with zero `# Pre:`/`# Post:` annotations — confirmed directly. This means the new `CONFLICT` state can fire even when PyProver's stream examined nothing at all, not just when it examined something and reached a different conclusion than another stream. Judged this as correct behavior to keep (a vacuous pass genuinely shouldn't be allowed to silently outrank a real captured crash — that's arguably a worse failure mode than the one this fix closes), but it's a real nuance worth knowing when reading a `CONFLICT` report: it does not always mean "two streams actively disagreed," sometimes it means "one stream found something and the other stream had nothing to say." Whether `ContractVerifier` itself should report something other than vacuous `True` for zero-annotation code is a separate, not-attempted-here question.

### 20.4 New chat links found (not previously catalogued in this document)

Searching for "old versions" to merge from surfaced chats beyond what §3/§5 already cited:

- [Pydebug skill testing and compliance review](https://claude.ai/chat/2401889e-d096-4ba4-8f05-c9949c253abb) — a second pydebug repackaging/compliance pass, not previously linked in §3.
- [Python debug skill testing and enhancement](https://claude.ai/chat/1492eee2-fa60-4c1c-97c3-a4b7ff7eb767) — **the important one**: fixes a real `sys.settrace()` timing bug in the "ENHANCED" pydebug build (the `"line"` event fires *before* the line executes, not after, so a naive tracer captures stale variable state for the line currently running). Fixed via a dual `final_state`/`final_state_raw` architecture and converting `exception_info` from a tuple to a dict. **Checked directly whether this fix is actually present in `src/python_debug/` as currently bundled — it is** (`final_state_raw` exists, `exception_info` is dict-shaped with `.get("exception_type")` access throughout `bug_patterns.py`), and re-verified with live execution this session (aliasing and mutation-history tests both produced correct post-execution values, not the stale pre-execution values the bug would have produced). So §3's "PRESENT and confirmed working" claim for pydebug holds, now confirmed against the specific bug this chat describes rather than just against feature-name presence — but the chat itself was missing from this document's citations until now, and belongs here for anyone tracing where that fix came from.
- [Master debug skill testing on forge neo](https://claude.ai/chat/222c9b8e-ecf8-41ec-97f1-dfc169c5f946) (already cited in §5) and [a companion review](https://claude.ai/chat/35beb6dc-4747-4f26-a503-b58116271ef8) comparing v1.0/v2.0/v3.0's respective strengths.
- [Skill file version comparison and legacy features](https://claude.ai/chat/f041cf0f-129d-4997-b4e9-c9795a8fe6c5) — describes a **master-debugger v4** (28KB) built after v3.0/v3.1, restoring v2.0's Phase 0 static-analysis bash commands and 13-point risk checklist, v1.0's workflow templates and anti-pattern guardrails, and v3.0's blind-spot model, all reframed around Claude's own capabilities rather than human-readable instructions. **Not previously mentioned anywhere in this document** — §5 only referenced v3.0. Not evaluated against the current code-based orchestrator this session (out of scope for this pass, which was about fixing the two bugs in §20.1); flagged here so a future session doesn't have to re-discover it. Two more related chats from the same investigation: [Testing master debug skill on forge neo](https://claude.ai/chat/5d88966a-7e68-4baa-bc24-df553dcff440) (v1.0→v2.0 redesign) and [a Forge Neo application walkthrough](https://claude.ai/chat/ce13a076-d3e3-4574-8d0f-dbf3df6882b6).

### 20.5 Test coverage added

11 new tests: `python_debug/tests/test_unhandled_exception_pattern.py` (6) and `master_debugger/tests/test_synthesis_conflict_resolution.py` (5). Two of the five orchestrator tests needed a second pass after their first version made wrong assumptions about pre-existing behavior (a hardcoded out-of-bounds index doesn't match `_detect_off_by_one`'s specific regexes; a `result`-referencing postcondition is only satisfiability-checked, not implication-checked, per `contract_verifier.py`'s own documented scope) — both corrected by testing the actual behavior directly rather than assuming, consistent with this document's standing methodology. Full suite observed locally: 391 passed, 57 skipped, 1 deselected, 0 failed (380 + 11, zero regressions).

## §21. Real-world Rust test (xfce4-rs), a genuine `rust_debug` false-positive fixed, and a version-string drift finding (2026-07-11)

### 21.1 What was tested and why

Asked to test this suite against real code from XFCE (GitHub). XFCE's own components (Thunar, xfce4-panel, xfwm4, etc.) are C/GTK, which this suite covers via `cpp_debug`/`c_debug`, not `rust_debug` — but `xfce-mirror/xfce4-rs` (the official Rust GTK bindings repo) is a genuine Rust codebase, so `rust_debug` was exercised against `xfconf/src/binding.rs`, a real FFI wrapper file (8 `unsafe` blocks, calls into `glib`/`crate::Channel`).

### 21.2 Real bug found and fixed: `rust_debug/borrow_checker.py`

Two compounding issues, both confirmed against real `rustc --error-format=json` output before any fix was written:

1. **Crash on null diagnostic codes.** `_parse_diagnostic()` did `diagnostic.get('code', {}).get('code', '')`. rustc legitimately emits `"code": null` on aggregate notes (e.g. the trailing `"aborting due to N previous errors"` line), so `None.get('code')` raised `AttributeError`, silently caught by the outer bare `except Exception` in `parse_borrow_checker_output()` and replacing **all** real diagnostics with one generic `compilation_error` entry — on `binding.rs` this discarded 27 legitimate, well-structured diagnostics down to nothing useful. Fixed: `code = (diagnostic.get('code') or {}).get('code', '')`, plus filtering out the no-code/no-span aggregate notes entirely before they're even classified.

2. **Dependency-resolution errors misclassified as borrow-checker violations.** `BorrowCheckerParser` compiles standalone with bare `rustc`, which can't see Cargo dependencies — so any real-world Rust file with external crate deps (i.e. nearly all real Rust) produces `E0432`/`E0433`/`E0405`-class "unresolved import/crate/trait" errors before rustc ever reaches the borrow checker. The pre-fix code treated any rustc error as a borrow-check violation: `binding.rs` was reported `RiskLevel.CRITICAL`, `"28 borrow checker violation(s)"` — none of which were actually about ownership/lifetimes. Fixed by adding a `category` field (`"borrow_check"` vs `"dependency_resolution"`) to each parsed diagnostic and threading it through `detect_patterns()` and `debug()`'s risk/confidence/summary logic. Post-fix, the same file reports `RiskLevel.LOW`, confidence `0.2`, and an explicit "borrow checker not verified" summary rather than a false CRITICAL.

Positive-control regression check: a genuine, dependency-free `cannot borrow as mutable` violation still correctly reports `CRITICAL`/confidence `0.8`/1 pattern — the fix narrows false positives without suppressing true ones.

### 21.3 A related, previously-dormant bug: `common/interop.py`

While tracing how `javascript_debug`'s `JavaScriptDebugger` gets resolved, found `LanguageDetector.get_debugger_for_language()` imports from a nonexistent `verification_debugging_suite` package in both its Python and JavaScript branches — same class of bug as the `src/__init__.py` absolute-import issue from an earlier session, just never caught because **nothing in the suite calls this method** (`master_debugger` doesn't route language detection through it at all). Fixed to relative imports (`..javascript_debug`, `..python_debug`); confirmed both branches now resolve correctly. Filed as dormant-but-real rather than live-and-wrong, since it had zero behavioral effect until now.

### 21.4 Version-string drift across the package (found, not fully fixed)

Cross-checking the fix above against "what version is this" turned up genuine drift between files that should agree:

| File | Claimed version | Accurate? |
|---|---|---|
| `CHANGELOG.md` | 2.9.4 | Yes — matches actual latest dated entry |
| `roadmap.md` (this file's own header) | 2.9.4 | Yes |
| `src/__init__.py` (`__version__`) | 2.6.1 | **No** — stale since before §19/§20's work |
| `INTEROP.yaml` (`version:`) | 1.2.0 | **No** — several major releases stale |
| `MANIFEST.txt` (header) | 2.9.1 | **No** — one release behind, and the file's own body text already flags *other* parts of itself as stale without noticing its own header is too |
| `SKILL.md` (frontmatter) | *(no version field present)* | N/A |

Not fixed this pass (would mean touching `src/__init__.py`'s single most-imported line, `INTEROP.yaml`'s machine-readable metadata, and `MANIFEST.txt`'s header, each with its own downstream consumers/audit implications) — flagged here so a version-bump pass can do all four consistently in one go rather than one at a time, which is exactly the kind of piecemeal drift that produced this discrepancy in the first place.

### 21.5 "Merge missing features from an older archive" — investigated, found to be a non-issue

Given a separately-uploaded older `debug-suite` archive (SKILL.md `version: 1.2.0`, no `rust_debug`/`cpp_debug`/`c_debug`/`assembly_debug`) and asked to merge anything missing from it into this branch. Full file-path diff (`comm -23` on sorted `find` output from both trees) found **zero files present in the 1.2.0 archive that are absent from this one** — every path in the older archive already exists here, plus ~80 more. Spot-checked the files both archives share (`pyprover/__init__.py`, `async_verifier.py`, `contract_verifier.py`, `troubleshooting/phases_5.py`, `javascript_debug/tests/...`) and in every case this branch's version was equal or strictly better (real relative-import fixes, a corrected async-heuristic false-positive, more verifier modules, more honest docstrings) — never worse. Conclusion: the 1.2.0 archive is a strict, older subset of this branch; there was nothing to merge. (An earlier attempt at this same comparison, before re-extracting cleanly, briefly overwrote this branch's newer `pyprover` v14.1 files with the 1.2.0 archive's older v14.0 ones — caught before packaging by noticing the file-count/content diff, reverted, and redone from a clean extraction. Noted here in case any downstream artifact from that intermediate state was ever shared; the delivered package does not contain it.)

### 21.6 `troubleshooting` merge: domain-awareness from the standalone skill

The standalone `troubleshooting` skill (a Claude-facing SKILL.md methodology doc, not code) has a 6-phase model with explicit Code/Hardware/General domain refinements. `troubleshooting/phases_5.py`'s `Troubleshooter.diagnose()` accepted a `context` parameter since its first version but never read it anywhere in the method body — domain had zero effect on classification or remediation. Merged in: `context` now actually branches Phase 2/3 logic across `code`/`hardware`/`general` (previously only `code`-shaped logic existed regardless of what was passed); Phase 0 now flags when the domain's single-most-diagnostic-indicator looks absent from the problem description (`evidence_sufficient`/`missing_evidence_prompt`) rather than just recording string length; the SKILL.md's Anti-Patterns table is now exposed as `Troubleshooter.ANTI_PATTERNS` data, not just prose a Claude session might separately have access to. No new test file exists for this module (confirmed pre-existing gap, not introduced here — `troubleshooting/` has no `tests/` directory at all, unlike every other component in this suite).

### 21.7 Stub inventory

Systematic grep (`TODO`/`FIXME`/`placeholder`/`stub`/`NotImplementedError`) across all of `src/`, hand-verified hit by hit. Full detail in `STUBS.md` (new file, ships alongside `roadmap.md`). Headline findings not otherwise covered in §1-§20:

- `rust_debug/phases.py`'s Phase 0 static analysis (`phase_0_static()`, `phase_0_ok`) is a hardcoded `True` — no AST inspection happens despite the name.
- `troubleshooting/diagnostics.py` (a *different* module from `phases_5.py`, above) is almost entirely stubbed — `HealthChecker.check_all_tools()` hardcodes every tool as `"healthy"` unconditionally, `UniversalTroubleshooter._suggest_fixes()` ignores its own input and always returns one canned response. Confirmed **dead**: nothing outside this file imports these three classes, and `troubleshooting/__init__.py` only exports from `phases_5.py`.
- `test_generator/test_generator.py`: `run_tests()` and `measure_coverage()` always return the same hardcoded zero/empty result regardless of input; `run_fuzzing()`'s `"coverage_estimate": 0.75` is a constant, not a measurement; and the generic test-body generator can emit literal `# TODO: Implement test` / `pass` into **user-facing generated output**, not just as an internal placeholder.
- `javascript_debug/__init__.py`'s `JavaScriptDebugger` class (the Python orchestration wrapper) is `pass`-stubbed on both its methods, even though the JS it's meant to wrap (`debug-engine.js`, `bug-patterns.js`) is real and substantial. Nothing in `master_debugger` currently wires JS debugging into the orchestrated pipeline at all.

Distinguished from genuinely-scoped, honestly-commented limitations that are *not* stubs: `pyprover`'s `NotImplementedError` exhaustiveness guards on unsupported AST node types (caught and degraded gracefully by every caller), and `assembly_debug`'s two documented "don't model stack memory" / "target not statically known" simplifications.

### 21.8 Test suite after this session's fixes

No new test files added this pass (would be the natural next step for `borrow_checker.py`'s categorization logic specifically, which — like the rest of `rust_debug` before v2.9.4 — has no dedicated test file of its own; `test_phase_2_formal.py` only covers `phase_2_formal`, not `borrow_checker.py`). Full suite after all fixes above, with `z3-solver`/`hypothesis` installed (without them, `pyprover/tests/{test_ghost_state,test_quantifiers,test_z3_builtins}.py` fail to collect — an environment gap, not a code regression): 383 passed, 57 skipped, 1 deselected, 0 failed. `src/common/tests/test_pyprover_bridge.py` fails to *collect* (`ModuleNotFoundError: No module named 'common'` — an absolute-import assuming a different `sys.path`/rootdir setup than this suite's own `pytest.ini` uses) independent of anything touched this session; not investigated further this pass.

## §22. Simplifier coverage: writes, zero division, free names, and the blocker list (2026-10-20, debug-skill branch contract-simplifier-fixes)

### 22.1 What was built in this pass

The `simplify_function` / `verify_function_equivalence` model in `src/pyprover/equivalence_verifier.py` now covers:

- Containers: `list[T]` and `dict[K, V]` parameters, list literals (including `[]`), reads guarded by path-checked obligations, and loops over lists unrolled up to `max_unroll` with a domain note (§22.3 below).
- `try`/`except` over index, key, None and zero-division failures, with a domain note for failures the handler does not catch.
- `Optional[T]` parameters, `is None` tests, `isinstance` on the modelled types, `float` as exact reals (with a note), and `bool` inferred for unannotated parameters used as conditions (with a note).
- Methods: reads and writes of scalar `self` fields. A method's final field state is part of an equivalence check.
- `raise` (excluded from the domain with a note), `import` (names are opaque), and `range(a, n)` with a symbolic bound (unrolled with a note).
- Division by a value that may be zero is rejected unless guarded or caught. The contract and loop translators refuse `/` by a non-literal.

### 22.2 Soundness fixes made in this pass

- Free names (module globals and unknown builtins) used to be read as unknown integers. A claim could then hold on a wrong model of that name. They are rejected now. Before the fix, those names were read as integers in 19 functions (`re`, `ast`) without any report. Now those functions are reported as unsupported for this reason.
- `x % -2` was proven equal to `x % 2` by the contract translator. Only a positive literal divisor is translated now.
- Field final states were looked up by the wrong key in the first version of the write support. Found by a test that compared two methods with different final states and got "equivalent".

### 22.3 The batch

`run_subset_batches.py` (kept in the scratch directory, not the repo) runs `simplify_function` over every function in the 85 non-test scripts in parallel batches of 10 on 4 workers. For each function it records the status, checks the translated Z3 expression against the source on a grid of inputs (for functions with at most three parameters and no containers), and checks any reported rewrite on the same grid. Methods are analysed inside their class.

Last run: 727 functions. 3 simplified (`estimate_async_overhead`, `estimate_ffi_overhead` are term reorderings; `confidence_percent` is a method over optional and float fields, checked against its Python logic). 14 already minimal. 710 unsupported. No translation or simplification mismatches.

### 22.4 Blockers, in order of frequency, and whether they can be lifted

1. **Parameter annotations naming classes or open types the body reads** (`VerificationState`, `Dict[str, Any]`, `LanguageType`, `Path`, `ControlFlowGraph`, `CodeStructure`, `ast.expr`, …): about 100 functions. Not feasible without a model of each class. Enums (`LanguageType`, `OperationType`) are feasible as finite sorts if the enum is in the analysed code; not done.
2. **Function ends without returning a value (None)**: about 16 `__init__` and setter methods. Out of scope: the model has no None return value.
3. **List literals in expressions** (`Unsupported AST node: List`): about 12. Returning or passing a list is not modelled. Lists in assignments are modelled.
4. **Expression statements** (calls for effect): about 11. Not feasible: calls have effects this model does not represent.
5. **`for x in ...` over non-range iterables**: about 10. Not feasible for iterables of unknown type; loops over container parameters are modelled.
6. **`None` tests on non-names** (`x.attr is None`, `f(x) is None`): about 10. Not feasible without call and attribute models.
7. **Global names** (`re`, `ast`, module constants): about 19. Correctly rejected (§22.2). Lifting this needs the module's values, which the batch does not pass.
8. **Fields typed by unknown values** (`self.state`, `self.report`, `self.results`, …): about 30. Feasible only with an annotation on the field or a parameter it is assigned from. Most of these are assigned from calls.
9. **Field annotations naming classes or open types** (`List[DetectedPattern]`, `Dict[str, List[str]]`, …): about 40. Not feasible without class models.
10. **f-strings** (`JoinedStr`): about 7. Not feasible: string formatting over unknown values.
11. **`self` passed as a value**: about 7. Not feasible: the object would escape to code the model cannot see.
12. **Nested class definitions, `class` attributes of unknown type, and empty-list fields**: about 20. Not feasible in general.
13. **Calls** (`Unsupported call: Attribute ...`): about 15. Not feasible without call semantics.

The top blockers are therefore dominated by annotations naming classes and by calls. Feasible next steps, each of which would lift a small number of functions: enum parameters (item 1, partial), and fields whose annotation is a scalar type (item 8, partial).

### 22.5 Test suite

New tests: `test_containers.py`, `test_container_loops.py`, `test_try_none_isinstance.py`, `test_floats_and_zero.py`, `test_object_fields.py`, `test_blockers_round.py`. Each construct is checked against Python on concrete inputs where the construct can be evaluated concretely. The full suite passes: 1195 tests, with the environment's `hypothesis` installed (the property-tester tests were failing only because it was missing).

## §23. Class and call models: removing the class and call blockers from §22.4 (2026-10-20)

### 23.1 What was built

The simplifier in `src/pyprover/equivalence_verifier.py` now reads a class and a call instead of stopping at them. The rules, and what each one excludes:

- **Objects.** A parameter, or a field, annotated with a class the code can reach is an object. Its scalar fields are symbols named `p.attr`, and its container fields are containers. An object is read-only: a method of the object that writes a field is not inlined, and a statement that writes a parameter's field is still rejected. A method's own `self` is the only writable object, as before.
- **Enums.** A plain `Enum` subclass with distinct int or str literal members is a finite value. Its members are compared with `==`, `!=`, `is` and `is not`, and two members of one enum are equal only if they are the same member. An enum value cannot be returned, passed where an int is expected, or rendered as Python, because its Z3 form is a member index.
- **Calls.** A call to a function the code can reach, or to a method of `self` or of an object, is inlined by symbolically executing the callee's body. The callee sees its parameters, its locals, and the fields of the objects it is given, at the values the caller sees (so a field written earlier in the caller is read as written). It cannot see the caller's locals. It is rejected if it writes a field, recurses (directly or through another call, to depth 8), is decorated, takes keyword or variable arguments, does not return on every path, or may raise.
- **Properties.** A property read is a call with no arguments.
- **Subclasses.** A method or field a subclass may override is not read on the base class, because the subclass's version could run. Subclasses are found by base-class name: across the repository when the scope is a `ProjectScope`, and in the analysed code alone otherwise (the domain of such a result says so).
- **Scope.** Names are resolved through `src/pyprover/project_index.py` (`ProjectScope`). An import is followed inside the repository, through package `__init__` re-exports, with a hop limit. A name imported from outside the repository is not resolved.
- **Rendering.** `simplified_python` renders scalar parameters and scalar fields as `p.attr` or `<self>.attr`. A list length, an enum, or a `None`-able value is not rendered, and falls back to the Z3 form.

### 23.2 Census

The census runs `simplify_function` on each function of the 83 non-test Python files in `src/` (`blocker_census.py`, kept in the scratch directory, not the repo, as §22.3 was). It deduplicates by name within a file, so it counts 656 functions where §22.3 counted 727 (different census, same files).

Status: 656 functions before and after. Simplified 3, already minimal 9, unsupported 644 before and 644 after. No function reached a status it did not have, and no function crashed.

The change shows in the first blocker of each unsupported function (`scratch_sim/measure.py`): a function that used to stop at a class is now stopped by a later construct, which is the intended effect.

| Blocker (first reason) | Before | After |
|---|---|---|
| Parameter annotated with a project class | 70 | 0 |
| Field annotated with a project class | 2 | 0 |
| Free name that is a project function or class | 24 | 0 |
| Field of unknown type | 128 | 104 |
| Call not modelled (built-in method, e.g. `.lower()`) | 10 | 11 |
| Object used as a value | 11 | 17 |

The rises are functions that now get past the class annotation and stop at a later construct. "Object used as a value" holds class constructors (`UnifiedDebugReport(...)`), a `self` passed to other code, and containers, none of which is a class or call model.

### 23.3 Blockers that remain, and why

1. **Constructors** (`Cls(...)` on a project class): constructing an object needs a model of the new object's fields, which this model does not build.
2. **Built-in methods** (`str.lower`, `str.split`, `list.append`, …): a string or container model is a separate piece of work. The §22.4 item 13 call blockers are of this kind.
3. **Containers as values** and **`self` passed to unmodelled code**: unchanged from §22.4 items 3 and 11.
4. **Nested objects** (a field of object type, such as `VerificationState.code_structure`): a field that holds an object is reported as not modelled. Modelling it needs prefixes for the field's own fields.
5. **Module-level constants** (§22.4 item 7): not part of this change, which is about classes and calls.
6. **Calls for effect** (§22.4 item 4): still rejected. A call that writes state the model does not represent cannot be inlined.

### 23.4 Soundness

Each rule that can make a claim is tested against Python on real inputs. The tests are in `src/pyprover/tests/test_class_and_call_models.py` (31 tests). A result that renders as Python is run on the original's inputs, with objects built from the class's fields and enum values taken from the real `Enum`. The tests also cover the rejections: a call that writes, a recursive call, a decorated call, a missing argument, a keyword argument, an object of the wrong class, an enum member used as a value, a subclass override, and a name the repository does not define.

Two assumptions are recorded where they apply rather than hidden. An object parameter is the class it is annotated with, unless a subclass exists (see above). A function compared with another has the same class definition only if both come from one code string or one scope. Otherwise the two sides are reported as having different types.

### 23.5 Test suite

Full suite after the change: 1226 passed, 58 skipped, 1 deselected (§22.5 reported 1195 passed; the 31 new tests account for the difference).
