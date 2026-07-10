# legacy_code/ - Recovered fragments from prior PyProver branches

## What this is

This folder contains **real code fragments recovered from conversation history** via `conversation_search`, for the features documented as missing in `roadmap.md`. It is not a complete, importable codebase - `conversation_search` returns text snippets from past chats, not full file downloads, so every file here is a **partial reconstruction**, often truncated mid-function where the search snippet cut off.

**Purpose:** a future agent restoring one of these features should start by reading the relevant fragment here instead of re-running `conversation_search` from scratch and re-discovering the same code. Treat each fragment as "this is what it looked like, verify and complete it" rather than "this is ready to import."

## What this is NOT

- Not tested. None of this code has been run in this session.
- Not necessarily compatible with the current `src/common/interop.py` types (`UnifiedDebugReport`, `BugPattern`, etc.) - all of it predates the unified-suite merge and used its own standalone data types (`VerificationResult`, `LoopVerificationResult`, etc.). Adapting it to current interop types is part of the restoration work, not already done.
- Not necessarily the *final* version of each feature - where a chat shows iterative patches, the fragment captured here is whatever the search query surfaced, which may be an intermediate state. Cross-check against `roadmap.md` §2 for the feature's full version history before assuming a fragment is final.

## Index

| File | Feature | Source branch | Roadmap section | Source chat |
|---|---|---|---|---|
| `pyprover_loop_invariant_v2_prototype.py` | Original `@loop_invariant` decorator + Hoare-logic `SymbolicExecutor.visit_While` (INIT/STEP/POST proof obligations) | Earliest prototype (pre-v6, "prover.py v2") | §2.1 | https://claude.ai/chat/11506dad-69d9-49f6-890d-b240a5768aa1 |
| `pyprover_v13_loop_verifier.py` | `loop_verifier.py` - regex-based extraction of `@loop_invariant(...)` across Python/C/C++/Java/C#, `LoopVerifier.verify_source()`, `LoopVerificationResult` | Branch B, v13.0 | §2.1 | https://claude.ai/chat/f076b379-5374-45c4-a796-67498d72f844 |
| `pyprover_v13_contract_simplifier.py` | `ContractSimplifier`, `ContractSimplificationResult`, `RemovedClause` - iterative Z3-implication redundant-clause removal | Branch B, v13.1 | §2.1 | https://claude.ai/chat/f076b379-5374-45c4-a796-67498d72f844 |
| `pyprover_js_nodejs_parser_fix.py` | Replace 39ms Python `esprima` JS parsing with a 3-4ms Node.js `acorn` subprocess call | Branch B, v13.1 bug-fix session | §2.2 | https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26 |
| `pyprover_multiline_contract_regex_fix.py` | Fix for `@requires(\n "a and "\n "b"\n)` not being extracted (single-line-only regex bug) | Branch B, v13.1 bug-fix session | §2.2 | https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26 |
| `pyprover_v11_adapters/` | **Real source** (not a `conversation_search` reconstruction — Max uploaded the actual `pyprover_v11_2.skill` archive on 2026-07-10, superseding the old `LANGUAGE_ADAPTER_GUIDE_recovered.md` fragment). The full `LanguageAdapter` 6-method interface (`interfaces.py`), 6 real per-language adapters (`adapters/python_adapter.py` — real `ast`-based parsing; `javascript_adapter.py`/`typescript_adapter.py` — regex/JSDoc, "for production use, integrate with @babel/parser" per its own docstring; `nasm_adapter.py`/`fasm_adapter.py`/`webassembly_adapter.py` — comment-annotation parsing), and the language-agnostic verification core (`verifier.py`, `PyProverCore`). See `pyprover_v11_adapters/FINDINGS.md` for two real bugs found and one fixed. | Real branch (v11.1-v11.2) | §2.2, §12.6 | (superseded upload, no longer a search reconstruction) |

| `pyprover_v8_2_core_with_real_template_invariants.py` | **Real source**, uploaded 2026-07-10 (`pyprover-v8-2.skill`). A `TemplateBase` class hierarchy (`ACCUMULATOR`, `BINARY_SEARCH`, `MIN_MAX_LOOP`, `RECURSION`, `STATE_MACHINE`, `FILTER`, `SCAN`, `WHILE_LOOP`) where each template is a dataclass with a real `generate_invariant()` method producing an actual invariant expression string (e.g. `MIN_MAX_LOOP.generate_invariant()` → `"{current_best} == min(arr[:i+1])"`) — this is what `pyprover_v11_adapters/verifier.py`'s `_min_max_constraints()` etc. *should* do and doesn't (Finding 2, see that folder's `FINDINGS.md`). Requires the template to be manually parameterized with variable-name bindings (`current_best`, `arr_var`, etc.) - v11.2's `infer_template()` detects *which* template applies but does not extract these bindings, so combining the two versions needs a third piece (binding extraction) that exists in neither as uploaded. Not integrated; cross-referenced from `pyprover_v11_adapters/FINDINGS.md`. | v8.2 (predates v11.x's adapter-based architecture) | §2.2, §12.6 | (superseded upload) |



Verified this against real Z3 test cases (not just read). Two findings, one fixed, one left as a documented limitation — see `pyprover_v11_adapters/FINDINGS.md` for the full detail:

1. **Soundness bug, fixed in `verifier_SOUNDNESS_FIXED.py`**: the original `Z3Verifier.verify()` checked whether preconditions+postconditions+template-constraints were jointly *satisfiable*, not whether the postcondition was *implied* by the preconditions. Since the relevant variables are typically under-constrained, this made almost any postcondition — including outright wrong ones — report `verified: True`. Reproduced (`@ensures("result < 0")` on a max-finder → `verified: True` before the fix), fixed (assert antecedent, negate the postcondition, check UNSAT — the same implication-check pattern this project's own `contract_simplifier.py`/`loop_verifier.py` already use correctly), and re-verified (same case now correctly reports `verified: False` with a counterexample; a genuinely-provable case still reports `verified: True`).
2. **Not fixed, architectural limitation, left as-is**: `_accumulator_constraints()`, `_binary_search_constraints()`, `_min_max_constraints()` are all empty-list stubs. The "10 verification templates" this system advertises contribute zero actual proof content even after the soundness fix — `template_type` is classification metadata only. This means the verification core only checks logical consistency between stated `@requires`/`@ensures` clauses, not that the code's actual loop/computation satisfies them — which is a substantially weaker guarantee than this project's own already-integrated `pyprover/loop_verifier.py` (real Hoare-logic INIT/PRESERVATION proof obligations tied to actual loop structure). **The genuinely valuable, non-duplicated part of this archive is the adapter/parsing layer** (multi-language contract extraction), not the verification core — a real integration should port the adapters but wire their extracted `Contract` objects into this project's existing (better) verification engine, not into `verifier.py`/`z3_verifier.py` as bundled here.

Not integrated into `src/pyprover/` this session — porting 6 languages' worth of adapters, converting to `common.interop` types, and rewiring them onto the existing verification core (rather than the weaker one bundled here) is a substantial, separately-scoped task. See roadmap.md §12.6.
| `verification_stack_and_bugs.md` | The 5-layer verification stack design (Static/Runtime/BMC/Property/Formal) + the 5 known bugs from the Chromium red-team session (Go package-scope regex, JS parser speed, multiline contracts, poor error messages, missing caching) | Branch B, v13.1 testing session | §2.2, §2.3 | https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26 |

## How to use this when restoring a feature

1. Read the fragment.
2. Read the linked source chat (use `conversation_search` with distinctive terms from the fragment, e.g. function/class names, to pull more context/surrounding code than what's captured here - the search snippets are not exhaustive).
3. Check `roadmap.md` §2 for the feature's full intended scope and version history (a fragment may be an intermediate patch, not the final state).
4. Port the logic into `src/pyprover/`, converting standalone result types to `common.interop.UnifiedDebugReport`/`BugPattern` the way `pyprover_bridge.py`'s `_adapt_local_result()` already does for `ContractVerifier`.
5. Write tests *before* declaring it done - every bug fixed in CHANGELOG 2.2.0-2.2.2 was found by actually running code against it, not by reading it. Don't repeat the mistake documented in `roadmap.md` §1 (a past audit claimed completeness it never verified).
