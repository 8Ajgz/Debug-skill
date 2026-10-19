# Debug Suite: Evolution and Feature-Loss Audit

> **Provenance:** all code in this repository was written by an unspecified version of Claude, unless a commit or file says otherwise.
>
> All commits from this account were made by Claude under the oversight of Maxwell Morrongiello.

**Scope:** the 114-entry archive `4ea504df-archive.zip` (debug-suite snapshots, pyprover, python-debug, javascript-debug, py-debug, verification-debugging-suite).
**Newest release in the archive:** debug-suite v2.9.6 (2026-07-11). The repo `8Ajgz/Debug-skill` on `main` holds v1.2.0 plus two fix commits, so it is several releases behind.
**Method:** each archive file was unpacked (zip-safe, no code run), its version read from SKILL.md frontmatter and CHANGELOG headings, and its top-level classes and functions compared by name against v2.9.6 with an AST scan. Body-level diffs were done only for the cases called out below.

---

## 1. Release sequence (debug-suite lineage)

| Version | Date | Archive snapshot | What changed |
|---|---|---|---|
| 0.5.0 | 2026-06-22 | none (CHANGELOG only) | Suite skeleton, partial components |
| 0.9.0 | 2026-06-23 | none (SKILL.md history only) | Beta: components integrated, docs added |
| 1.0.0 | 2026-06-24 | `verification-debugging-suite-v1.0.0.skill` | Master-debugger-v5 4-phase orchestrator; phases 0 to 2 |
| 1.0.1 | 2026-06-24 | `verification-debugging-suite-v1_0_1-UPDATED.skill` | Circular import fixed in `master_debugger/phases.py`; first pytest.ini and 80+ tests |
| 1.1.0 | 2026-06-24 | `verification-debugging-suite-v1.1.skill` | Consolidation: root conftest, API.md, INTEROP.yaml, openapi.yaml, MANIFEST.txt |
| 1.2.0 | 2026-06-28 | `debug-suite-v1_2.skill` | JavaScript debug merged; master-debugger handles Python and JS |
| 2.0.0 | 2026-06-28 (inferred, no date recorded) | `debug-suite-v2_0.skill` | PyProver v12 bridge across 12 languages. Its CHANGELOG top entry still reads 1.1.0 (version drift) |
| 2.1.0 | 2026-06-28 | `debug-suite-v2_1.skill` | PyProver bridge (Phase 1); Rust borrow-checker parser and clippy (Phases 2 to 3) |
| 2.2.0 | 2026-06-30 | `debug-suite-v2_2.skill` | C/C++ debug (Phase 4): clang diagnostics and clang analyzer. Suite at 144/144 |
| 2.2.1 to 2.2.4 | 2026-06-30 | not archived separately | pyprover package import fixed; placeholder bridge result replaced; AsyncVerifier wired in; `legacy_code/` and `roadmap.md` added |
| 2.2.5 | 2026-06-30 | `debug-suite.skill` | SKILL.md frontmatter made valid for skill-creator; packaging via official tools |
| 2.6.0 | 2026-07-09 | `debug-suite-8.skill` (its top entry is 2.6.1) | `src/__init__.py` was empty and is now real; test_generator import fixed; Rust false-confidence fixed; CBMC 6.x flags fixed |
| 2.6.1 | 2026-07-09 | `debug-suite-8.skill` | Three RiskLevel enums unified; bandit detection fixed; semgrep added (adds ~6 to 8 s per call) |
| 2.7.0 | 2026-07-10 | none | Reconciled with a sibling v2.5.2 branch; MasterDebugger exported; phantom `hypothesis` requirement removed |
| 2.8.0 | 2026-07-10 | none | `ContractVerifier` stub replaced with a real Z3-backed implementation |
| 2.9.0 | 2026-07-10 | `debug-suite-13.skill` | `EquivalenceVerifier` (code-to-code equivalence) |
| 2.9.1 | 2026-07-10 | `debug-suite-13.skill` | Two real stubs found by body-diff; methodology gap disclosed |
| 2.9.2 | 2026-07-10 | none | Quantifiers and ghost state (PyProver v14.2) |
| 2.9.3 | 2026-07-10 | `debug-suite-19.skill` | `len()`, `abs()`, `min()`, `max()` and string predicates |
| 2.9.4 | 2026-07-10 | `debug-suite-28.skill` | Two synthesis bugs in bug-pattern dispatch and orchestrator aggregation |
| 2.9.5 | 2026-07-11 | `debug-suite-fixed-v2.9.5.skill` | Every STUBS.md item fixed; version strings reconciled |
| 2.9.6 | 2026-07-11 | `debug-suite-14.skill` | Regression fix; pytest testpaths now includes top-level `tests/` |

Only snapshot-backed releases can be reproduced from the archive. The 0.5.0, 0.9.0, 2.2.1 to 2.2.4, 2.7.0, 2.8.0 and 2.9.2 entries are documented in the CHANGELOG only.

### Growth

| Snapshot | Top-level named definitions (non-test) | Notes |
|---|---|---|
| 1.0.0 | 138 | Master-debugger, python-debug, pyprover |
| 1.1.0 | 133 | Consolidation release |
| 1.2.0 | 143 | JavaScript merged |
| 2.2.0 | 161 | C/C++ added |
| 2.6.1 | 229 | Rust, semgrep, bandit |
| 2.9.6 | 284 | 19 components, 12+ languages |

These counts are a rough size measure, not a feature count.

---

## 2. Component lineages (before they were merged)

| Component | Archive files | Versions | Status in v2.9.6 |
|---|---|---|---|
| **pyprover** | about 45 files (`pyprover*.skill`, `pyprover_v11_2*`, `pyprover_revised_roadmap*`) | v1 through v11.2 and v14.0.0 variants; roadmap doc dated 2026-06-22 | Merged as `src/pyprover/`. Three divergent branches (roadmap §1): A (v6.1 to v7.0, library integrations), B (v8.x to v11.2, multi-language adapters), C (the merged one, "v14.0") |
| **python-debug** | 14 files (`python-debug*`, `py-debug*`) | v12.2.0, v12.3.0, ENHANCED and FIXED variants | Merged as `src/python_debug/`. Standalone examples (`EXAMPLES_v12_2.py`, 8 examples) not carried over |
| **py-debug** | 2 files | v2.0, single-file skill | Its features (line tracking, alias detection, root cause) are covered by python_debug |
| **javascript-debug** | 6 files | v1.0 | Merged in 1.2.0 as `src/javascript_debug/` |
| **verification-debugging-suite** | 20 files | 0.5.0 to 2.0.0 (name used until the debug-suite rename); the 2.0.0 file is "Six Independent Skills" | Superseded by the debug-suite lineage |

---

## 3. Feature-loss audit: what older code had that v2.9.6 lacks

Method: AST symbol names from every archive snapshot, minus the names defined in v2.9.6, then checked against the roadmap's own list of missing items. Names are a first filter only. A name match does not prove the body is the same (see CHANGELOG 2.9.1).

### 3.1 Debug-suite lineage
Every top-level symbol defined in any debug-suite snapshot also exists in v2.9.6 (0 missing by name). Body-level differences were not checked for every symbol, so a same-named stub is still possible (CHANGELOG 2.9.1 found two such stubs).

### 3.2 Standalone pyprover (127 names absent from v2.9.6)

| Feature | Old source | Still missing in v2.9.6? | Disposition |
|---|---|---|---|
| SHA256 result caching | roadmap §2.1 (v13.0, no code recovered) | Yes | **Candidate:** small, worth porting |
| Parallel batch verification | `pyprover-10/scripts/parallel_verifier.py` (180 lines, ThreadPool, built on the v11 adapter interface) | Yes. The bridge's `batch_verify()` is sequential | **Candidate:** re-implement on `ContractVerifier`, do not copy |
| SMT-LIB export | `pyprover-v7-0/.../prover_extended_v7_0.py` `SMTLibExporter` | Yes | **Candidate, but do not port the old code.** It declares fixed `x`/`result` variables and pastes contract strings raw, so it is a stub. Use `solver.to_smt2()` from the real Z3 solver |
| Coq and Lean 4 export | same file, `CoqExporter`, `Lean4Exporter` | Yes | Not recommended: same stub pattern as SMT-LIB |
| Hypothesis property-based testing | `pyprover-10/scripts/property_tester.py` (511 lines, Python path uses Hypothesis) | Yes. roadmap §2.4 lists it, and `requirements.txt` says it is a future dependency | **Candidate:** Python path only, optional dependency |
| Invariant templates (BINARY_SEARCH, RECURSION, MIN_MAX, ACCUMULATOR, SCAN, FILTER, WHILE, STATE_MACHINE) | `legacy_code/pyprover_v8_2_core_with_real_template_invariants.py` | Yes. Each template has a real `generate_invariant()`, but they need variable bindings that were never recovered | Open. Needs binding extraction first |
| `@unroll_loops`, `@state_tracking`, `@assume` decorators | v8.2 core | Yes | Not worth porting: they only set function attributes and do nothing else |
| Conditional postconditions (`if cond: ensure` as Implies) | roadmap §2.1 (v13.0), v6 `z3_verifier.py` (regex-only, identifier conditions) | Yes | **Ported:** `# Post: if <cond>: <clause>` parsed with Python's own parser, checked as Implies in the verifier, simplifier and property tester |
| Float precision (`FloatWorkAround`, `scale_float`) | v6.1 / v7.0 | Yes. Floats were silently checked as integers | **Ported differently:** floats and float-annotated or float-adjacent variables are Z3 Real, `/` is real division, `//` and `%` are skipped over reals. Fixes three wrong verdicts (tests in `test_float_precision.py`) |
| Per-language adapters: C, Java, Go, C#, C++, Rust, TS, WASM, NASM, FASM | `pyprover-10`, `legacy_code/pyprover_v11_adapters/` | Yes, as PyProver adapters | Superseded: c_debug, cpp_debug, rust_debug, assembly_debug and javascript_debug cover these languages with real toolchains. Not ported |
| Ownership and permission model | `pyprover-skill` (`PermissionModel`, `OwnershipAnalyzer`) | Yes | Superseded by the Rust borrow-checker parser; not verified against C/C++ |
| v1 pipeline stages (`stage_fuzz`, `stage_triage`, `stage_coverage`, ...) | `pyprover-1/scripts/pipeline.py` | Yes | Superseded by master-debugger phases |
| `CoreVerifier`, `PhaseResult` | `verification-suite-complete` | Yes | Superseded |
| SymPy, beartype, Pydantic | Branch A (v6.2 to v7.0) | Yes | Not restored: library choices, not features |
| Proof artifact export (Phase 3D), contract inference (Phase 4) | roadmap §2.1, planned for v15.0 | Never built | Not old code; open roadmap work |
| tree-sitter | roadmap §12.2 | Not built | Decided no-go for the suite-wide framing |

### 3.3 Already merged, verified present
Equivalence checking (2.9.0), quantifiers and ghost state (2.9.2), `len`/`abs`/`min`/`max` (2.9.3), contract simplifier, loop verifier INIT/PRESERVATION, multi-language bridge, and the python-debug examples in `examples.py`.

---

## 4. Problems found in v2.9.6 during this audit

1. **`pytest` alone fails at collection.** `src/common/tests/test_pyprover_bridge.py` imports `common.pyprover_bridge`, which needs `PYTHONPATH=src`. `pytest.ini` has no `pythonpath` setting. With `PYTHONPATH=src`, the suite gives 520 passed, 22 skipped, 1 deselected. The CHANGELOG reports 482 passed and 60 skipped; the difference is the optional tools installed here.
2. **Version strings still disagree** in several files. Roadmap §21.4 records this, and 2.9.5 was meant to fix it. `INTEROP.yaml` and `MANIFEST.txt` were not re-checked in this audit.
3. **2.0.0 has no date** in its snapshot, and its CHANGELOG top entry is 1.1.0.

## 5. What this means for the earlier repo work

- The v1.2.0 archive I pushed to `8Ajgz/Debug-skill` is not the latest. The archive's v2.9.6 is. (v1.2.0 itself was released 2026-06-28.)
- The problems I fixed in that repo (missing `src/__init__.py`, the test `__init__.py` files, the stale `verification_debugging_suite` import, `RiskLevel.LOW`) are already fixed in v2.2.0 and later. Those fixes are superseded.

## 6. Merge plan and what was done

Approved by the user, then executed on `8ajgz/Debug-skill` `main`:

1. **History rebuilt.** The 13 snapshot releases from §1 are commits on `main`, one per release, dated to its release (2.0.0 is inferred). The final tree matches the v2.9.6 snapshot file for file. The two earlier commits (the v1.2.0 upload and its fixes) remain in history below them.
2. **`pytest.ini`** now sets `pythonpath = src .`, which fixes problem 4.1.
3. **Ported features**, each with tests, all in `src/pyprover/`:
   - `verification_cache.py`: SHA256-keyed, bounded LRU result cache.
   - `parallel_verifier.py`: batch verification in worker processes (Z3 is not thread-safe on its default context, so threads were not used). Cache hits skip the workers.
   - `smtlib_export.py`: SMT-LIB v2 scripts from Z3's own `to_smt2()`. Tests re-solve each script and compare with `verify_contract`. The old v7.0 exporter was not ported because it was a stub.
   - `property_tester.py`: Hypothesis-based contract testing for Python functions. Clauses are evaluated by a whitelisted AST walker, not `eval()`. Hypothesis is optional.
   - `invariant_templates.py`: BinarySearchBounds, MinMaxLoop, SumAccumulator, FilterCount, Scan, StateMachine. RECURSION and WHILE_LOOP were dropped (§3.2 explains why). Tests check each invariant against a reference loop at every iteration. These are runtime checks, not proofs.
4. **Bug found and fixed in the process:** `rust_debug/borrow_checker.py` ran `rustc <file>` without an output option, so every Rust check wrote a linked binary into the current working directory. It now passes `--emit=metadata --out-dir <tempdir>`. Borrow checking still runs.

**Still open** (not ported, recorded here): Coq and Lean 4 export, proof artifacts (Phase 3D), contract inference (Phase 4), and the v11 language adapters for PyProver itself (superseded by the per-language modules).
