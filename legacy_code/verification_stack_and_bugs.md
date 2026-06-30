# PyProver v13.1: 5-Layer Verification Stack + Known Bugs (RECOVERED)

**Source:** https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26 ("Testing pyprover on chromium codebase")

This chat actually ran the full stack below against 4 real Chromium-style
functions (Python `IntToHexString`, C++ `IsWellKnownPort`, JavaScript
`IsPrivilegedPort`, Rust `sum_array`) and got 100% verification success
(4/4) in under 350ms total. It also installed CBMC v5.95.1 for real in that
session's sandbox. Per roadmap.md §7, CBMC is confirmed installable in this
suite's current environment too.

## The 5-layer stack

```
Layer 5: FORMAL VERIFICATION      Z3, cvc5 fallback, loop invariants
         "Is the ALGORITHM correct for ALL inputs?"
         ↓ Symbolic proofs guide property tests
Layer 4: PROPERTY TESTING         Hypothesis (Python), Node.js (JS), cargo test (Rust)
         "Does code ACTUALLY behave correctly at runtime?"
         ↓ Concrete tests validate formal proofs
Layer 3: BOUNDED MODEL CHECKING   CBMC, KLEE (C/C++ exhaustive path analysis)
         "Are all paths safe within bounds?"
         ↓ Exhaustive path analysis
Layer 2: RUNTIME DETECTION        ASan, UBSan, compiled assertions
         "Are there MEMORY ERRORS during testing?"
         ↓ Actual execution with instrumentation
Layer 1: STATIC ANALYSIS          mypy, pylint, GCC, Clang, rustc
         "Are there obvious BUG PATTERNS?"
```

## Tool inventory confirmed working in that session's sandbox

| Layer | Tool | Language | Confirmed working |
|---|---|---|---|
| 1 | mypy, pylint | Python | yes |
| 1 | GCC | C++ | yes |
| 1 | Node.js | JavaScript | yes |
| 1 | rustc | Rust | not installed in that session (expected to work) |
| 2 | pytest | Python | yes |
| 2 | GCC (compiled) | C++ | yes |
| 3 | CBMC | C/C++ | yes, after `apt-get clean && apt-get update` fixed a corrupted apt cache |
| 3 | KLEE | C/C++ | not installed in that session - not attempted after CBMC succeeded |
| 4 | Hypothesis | Python | yes (real library, not the suite's own - see roadmap.md §1 phantom-dependency finding) |
| 5 | Z3 | all 12 | yes |
| 5 | cvc5 | all 12 (fallback) | yes |

**Installation commands recorded for CI/production deployment:**

```bash
# Layer 1: Static Analysis
pip install mypy pylint
npm install eslint
apt-get install clang-tools rustc

# Layer 2: Runtime
pip install pytest
apt-get install valgrind

# Layer 3: Model Checking
apt-get install cbmc klee

# Layer 4: Property Testing
pip install hypothesis
```

## 5 known bugs found in this system (not yet fixed in any branch)

1. **Go adapter: package-scope functions not detected.** The function-detection regex only matched method-style declarations, missing plain package-level `func Foo(...)` definitions. Identified as highest priority fix in that session.
2. **JavaScript parsing 10x too slow** (39ms vs 3-4ms via Node.js subprocess). Fix drafted in `pyprover_js_nodejs_parser_fix.py` (this folder).
3. **Python multiline contract extraction fails.** Fix drafted in `pyprover_multiline_contract_regex_fix.py` (this folder).
4. **Poor error messages** - Z3 `unsat` results weren't translated into actionable counterexamples with suggested fixes. (A later, separate "Better Error Messages" design - target output format and effort estimate - was also found; see the `pyprover_v13_loop_verifier.py`/`pyprover_v13_contract_simplifier.py` docstrings in this folder for the general pattern PyProver uses for human-readable result summaries, which this bug-fix would have extended.)
5. **Missing caching optimization** - same function re-verified from scratch on every call. (Branch B's v13.0 *did* add SHA256 result caching per roadmap.md §2.1 - this bug report may predate that fix, or that fix may not have made it into the same codebase this bug was filed against, given the branch-fragmentation problem documented in roadmap.md §1. Verify which is true before assuming this is resolved.)

## 4 "smart features" proposed in the same session, not built anywhere

- Automated contract strengthening from counterexamples
- Counterexample-driven test generation (this one *did* get built, but inside `test_generator`, not pyprover - see roadmap.md §4/§5)
- Batch parallel verification for 1000+ functions (overlaps with Branch B's `parallel_verifier.py`, see `pyprover_v13_loop_verifier.py`'s sibling file note in roadmap.md §2.1 - not recovered as code in this folder, search conversation history for "parallel_verifier.py ThreadPoolExecutor" for the docstring-level fragment that *was* found)
- Interactive contract debugger
