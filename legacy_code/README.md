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
| `LANGUAGE_ADAPTER_GUIDE_recovered.md` | Architecture doc: the `LanguageAdapter` 6-method interface (`language_name`, `parse_function`, `extract_contracts`, `extract_variables`, `extract_loops`, `infer_template`) and the 10 verification templates every adapter must detect | Branch B, v11.0-v11.2 | §2.2 | https://claude.ai/chat/d0b4e00c-15af-4cf8-bdf7-219dee000dc2, https://claude.ai/chat/c9d14d64-a052-48ff-9b3e-b6b8826a0736 |
| `verification_stack_and_bugs.md` | The 5-layer verification stack design (Static/Runtime/BMC/Property/Formal) + the 5 known bugs from the Chromium red-team session (Go package-scope regex, JS parser speed, multiline contracts, poor error messages, missing caching) | Branch B, v13.1 testing session | §2.2, §2.3 | https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26 |

## How to use this when restoring a feature

1. Read the fragment.
2. Read the linked source chat (use `conversation_search` with distinctive terms from the fragment, e.g. function/class names, to pull more context/surrounding code than what's captured here - the search snippets are not exhaustive).
3. Check `roadmap.md` §2 for the feature's full intended scope and version history (a fragment may be an intermediate patch, not the final state).
4. Port the logic into `src/pyprover/`, converting standalone result types to `common.interop.UnifiedDebugReport`/`BugPattern` the way `pyprover_bridge.py`'s `_adapt_local_result()` already does for `ContractVerifier`.
5. Write tests *before* declaring it done - every bug fixed in CHANGELOG 2.2.0-2.2.2 was found by actually running code against it, not by reading it. Don't repeat the mistake documented in `roadmap.md` §1 (a past audit claimed completeness it never verified).
