Reconcile the version-string drift found in roadmap.md §21.4 (bump `src/__init__.py`, `INTEROP.yaml`, and `MANIFEST.txt` to agree with `CHANGELOG.md`/`roadmap.md`'s accurate 2.9.4+, in one pass, all four files together), then work through the stub inventory in `STUBS.md` in priority order (§ below), starting with `rust_debug/phases.py`'s Phase 0 stub since it's the smallest and most self-contained.

---

## Header

- **Status:** In progress — this session fixed one real bug (rustc false-positive in `rust_debug`), one dormant bug (`common/interop.py` import path), merged `troubleshooting` domain-awareness, and produced a full stub inventory; none of the stub-inventory items themselves are fixed yet.
- **Date:** 2026-07-11
- **Scope:** `debug-suite` skill package (all components)
- **Tools used:** bash (rustc/apt/pip installs, pytest), file edit tools, web search/fetch (to pull real xfce4-rs code from GitHub for the test that started this session)
- **Reference:** this chat. No prior-chat search was run this session (see Past-Chat Review Instruction below for why that matters for the receiving instance) — roadmap.md's own extensive chat-URL citations (§1-§20) remain the authoritative source-chat index and are not duplicated here.
- **Written by:** Claude Sonnet 5
- **Effort:** extended reasoning throughout (real rustc invocation, real test runs, real file-diffing — no claims in this document are from memory/inference alone)
- **Companion file:** No — everything material from this session is already captured in full in `roadmap.md` §21 and `STUBS.md`, which ship alongside this handoff and are the actual source of truth, not summarized copies of it.

## Executive Summary

This session ran `rust_debug` against a real Rust file pulled from GitHub (`xfce-mirror/xfce4-rs`), found and fixed a genuine false-positive bug in `borrow_checker.py` (dependency-resolution errors were being misreported as CRITICAL borrow-checker violations), found and fixed a dormant wrong-import-path bug in `common/interop.py`, merged the standalone `troubleshooting` skill's domain-aware methodology into `troubleshooting/phases_5.py` (previously accepted a `domain` parameter it never used), and produced `STUBS.md` — a full, hand-verified inventory of every stub/placeholder/hardcoded-fake-result in the codebase. It also investigated and closed out a separate claim (from earlier in this conversation) that an older 1.2.0 archive had features missing from this branch — it doesn't; that archive is a strict, older subset.

## Continue-From-Here

Start with `STUBS.md`'s **STUB** section, in this order (smallest/most isolated first): (1) `rust_debug/phases.py`'s `phase_0_static()`/`phase_0_ok` — currently hardcoded `True`, needs a real AST-level check or an honest rename/removal if Phase 0 genuinely isn't meaningful for Rust; (2) `test_generator/test_generator.py`'s `run_tests()`/`measure_coverage()` — wire up real `pytest`/`coverage.py` invocation, matching the honest-degradation pattern already used elsewhere in this suite (rustc/clippy/clang availability checks) rather than a silent hardcoded zero; (3) decide whether `troubleshooting/diagnostics.py`'s three dead-stub classes (`UniversalTroubleshooter`, `ToolDiagnostician`, `HealthChecker`) should be deleted (nothing imports them) or actually implemented — don't leave them shipping silently either way without a decision recorded here or in roadmap.md.

## Objective Tracking

**Current objective:** Work through `STUBS.md`'s stub inventory, starting with the three items named above in Continue-From-Here.

**Past objectives (this session, chronological):**
1. Test `debug-suite` against real xfce code from GitHub — completed; led to finding the `rust_debug` false-positive (roadmap.md §21.1-21.2).
2. "Fix the code, update the skill, try again" — completed; verified with a positive control (genuine borrow violation still correctly flagged) and a full clean-room repackage/reinstall test.
3. "Merge missing content from [an older debug-suite archive] into the newer version" — investigated and closed as a non-issue (roadmap.md §21.5): the older archive has zero unique content. An intermediate mistake during this investigation briefly overwrote this branch's newer `pyprover` files with the older archive's — caught before packaging, reverted, redone cleanly. Superseded by the correct finding; not a live concern.
4. "Merge in any relevant missing content" from two further uploaded skills (standalone `troubleshooting` and `javascript-debug`) — `javascript-debug` had zero content diff (already byte-identical, bundled version just lacks the standalone's own `SKILL.md` wrapper, which doesn't apply in a bundled context); `troubleshooting` had a real, merged gap (roadmap.md §21.6).
5. "Document any stubs anywhere in the code" — completed, `STUBS.md`.
6. "Update this roadmap and handoff" — in progress; this document and roadmap.md §21 are that update.

## Past-Chat Review Instruction

This session did not run `conversation_search`/`recent_chats` — all findings above came from direct inspection and execution of the files in this session's working copy, not from historical claims. **Before continuing implementation on any `STUBS.md` item, search for it anyway**: several past "completeness audits" in this suite's history have been wrong (see roadmap.md §1's warning about the `Verification debugger suite completeness review` chat), so don't assume a stub found this session is new just because it wasn't mentioned in roadmap.md §1-§20 — search first, then trust direct testing over any claim (including this document's) if they conflict. Confirm on disk whether a given `STUBS.md` item has already been half-addressed in a session this document doesn't know about, the same discipline roadmap.md itself has needed repeatedly (e.g. §20's orchestrator bugs, found only by testing despite the code "looking" complete).

## Architecture

No architectural changes this session — every fix was a bug fix or a same-file enrichment within an existing component (`rust_debug/borrow_checker.py`, `rust_debug/phases.py`, `common/interop.py`, `troubleshooting/phases_5.py`), not a new component or a new integration point. `STUBS.md`'s DEAD-tagged items (`troubleshooting/diagnostics.py`'s three classes, and — before this session's fix — `common/interop.py`'s `LanguageDetector.get_debugger_for_language`) are notable precisely because they reveal parts of the architecture that were never actually wired together: `javascript_debug` has no path into `master_debugger`'s orchestration at all, live or dead.

## Implementation Roadmap

Carried forward from `STUBS.md` (new, this session) — no prior roadmap existed for these specific items:

- **Phase A** (~20-40 LOC): `rust_debug/phases.py` Phase 0 — either a real minimal AST check (mirroring the shape of `python_debug`'s Phase 0) or an honest removal/rename if Rust genuinely doesn't need one.
- **Phase B** (~60-100 LOC): `test_generator/test_generator.py`'s `run_tests()`/`measure_coverage()` — real `pytest`/`coverage.py` subprocess invocation with the same tool-availability-aware confidence scoring convention used in `rust_debug`/`cpp_debug`.
- **Phase C** (~10 LOC or a deletion): `troubleshooting/diagnostics.py` — decision + action (implement or remove).
- **Phase D** (~30-50 LOC, lower priority): reconcile the four-way version-string drift (roadmap.md §21.4).
- **Phase E** (not scoped this session): decide whether `javascript_debug` should be wired into `master_debugger`'s orchestration pipeline at all, given its Python wrapper class is currently a stub with no live caller either way.

## Complete API

N/A: this handoff is about fixing existing stubs and reconciling drift, not building new classes — `STUBS.md` names the exact functions/classes (`phase_0_static`, `run_tests`, `measure_coverage`, `HealthChecker.check_all_tools`, etc.) and their current file locations; no new signatures are being proposed here.

## Test Strategy

`rust_debug` (the component actually touched this session) has no dedicated test file for `borrow_checker.py` specifically — `test_phase_2_formal.py` only covers `phase_2_formal`. A `test_borrow_checker.py` covering the category-split fix (dependency-resolution vs. real borrow-check errors) should be the first test-debt item addressed, ideally before Phase A-C above, so future changes to `borrow_checker.py` have a regression net. Target: 5-8 tests (null-code diagnostic handling, each `DEPENDENCY_RESOLUTION_CODES` entry classified correctly, a positive-control real violation, aggregate-note filtering).

## File Structure

No change to the package's file structure this session. New files added at the package root: `STUBS.md`, this `debug-suite-handoff.md` (regenerated in place). `roadmap.md` extended with §21, not restructured.

## Workflow

Standard for this suite: implement the fix in the relevant `src/<component>/*.py` file → add/extend tests in that component's `tests/` directory → run the full suite (`python3 -m pytest src/ -q --ignore=src/common/tests/test_pyprover_bridge.py`; that one file fails to *collect* for reasons unrelated to any of this session's changes, see roadmap.md §21.8) → confirm zero regressions against the 383-passed baseline this session ends on → update CHANGELOG.md and roadmap.md in the same pass, not as an afterthought (this suite's own history — e.g. roadmap.md §1's warning — shows what happens when documentation and code drift apart) → repackage and `present_files`.

## Success Criteria Checklist

- [ ] Version strings agree across `src/__init__.py`, `INTEROP.yaml`, `MANIFEST.txt`, `CHANGELOG.md`, `SKILL.md`
- [ ] `rust_debug` Phase 0 either does real work or is honestly documented as a no-op and not called "static analysis"
- [ ] `test_generator`'s `run_tests()`/`measure_coverage()` either do real work or degrade honestly (matching the rest of the suite's tool-availability convention) instead of silently returning hardcoded zeros
- [ ] `troubleshooting/diagnostics.py` decision made and recorded (implemented or removed, not left ambiguous)
- [ ] `borrow_checker.py` has dedicated test coverage
- [ ] Full suite still passes with zero regressions against this session's 383-passed/57-skipped/1-deselected/0-failed baseline

## Edge Cases / Known Risks

- `z3-solver`/`hypothesis` must be installed (`pip install z3-solver hypothesis --break-system-packages`) or three `pyprover` test files fail to *collect* (not fail — collection error), which can look like a bigger regression than it is if the environment difference isn't noticed first.
- `src/common/tests/test_pyprover_bridge.py` fails to collect regardless of the above (`ModuleNotFoundError: No module named 'common'`, an absolute-import mismatch with this suite's own `pytest.ini` rootdir) — pre-existing, unrelated to anything in this session, not yet root-caused.
- Any future "merge features from an older archive" request for this suite should re-run the exact file-path-diff check from roadmap.md §21.5 (`comm -23` on sorted `find` output from both trees) before assuming there's something to merge — this session's experience is that assuming there is one, without checking, is exactly how the older-file-overwrite near-miss happened.
