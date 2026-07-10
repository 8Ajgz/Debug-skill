# Findings: `pyprover_v11_2.skill` audit (2026-07-10)

Source: `pyprover_v11_2.skill`, uploaded directly by Max (not a `conversation_search`
reconstruction). Extracted, imported, and run against real test cases in an
isolated sandbox before any integration decision was made.

## Finding 1: soundness bug in `Z3Verifier.verify()` — FIXED here

**Original code** built one Z3 solver, asserted preconditions + postconditions +
template-shape constraints all together, and checked `solver.check() == sat`.

That answers "does some assignment exist where all of these hold at once" —
not "does the postcondition follow from the precondition." Since the function's
variables (`result`, `max_val`, etc.) are otherwise-unconstrained Z3 integers,
the solver can almost always find *some* satisfying assignment regardless of
whether the stated postcondition is actually true of the code.

**Reproduction (before fix):**
```python
code = '''
@requires("len(arr) > 0")
@ensures("result < 0")
def find_max(arr):
    max_val = arr[0]
    for i in range(1, len(arr)):
        if arr[i] > max_val:
            max_val = arr[i]
    return max_val
'''
# core.verify(code, 'find_max') -> verified: True   (WRONG - result is never
# guaranteed negative for a max-finder; this should not verify)
```

**Fix** (`verifier_SOUNDNESS_FIXED.py`, apply to `z3_verifier.py`):
`generate_constraints()` now returns `(antecedent, postconditions)` instead of
one flat list. `verify()` asserts the antecedent, asserts `Not(postcondition)`,
and checks `UNSAT` — the standard validity-via-negation pattern already used
correctly elsewhere in this project (`pyprover/contract_simplifier.py`'s
`_implies`, `pyprover/loop_verifier.py`'s PRESERVATION check). Also added the
same bare-identifier Bool/Int guard fixed in `contract_simplifier.py` earlier
the same session (`parse_contract_expression`'s `eval()` returns a Z3
`ArithRef` for a bare-name clause, not a `BoolRef`; `z3.Not()` on that raises).

**Re-verified after fix:**
- The false-positive case above now correctly reports `verified: False` with
  a Z3 counterexample.
- A genuinely-provable case (`@requires("len(arr)>0") @ensures(...)` where the
  postcondition truly is implied by the antecedent) still reports
  `verified: True`.
- A bare-identifier `@ensures("result")` clause no longer crashes — reports
  `verified: False` with a clear "not a valid predicate" message instead.
- An unannotated function (no `@requires`/`@ensures` at all) still reports
  `verified: True` with "no postconditions to verify," matching the
  original's behavior for the no-postcondition case (there's nothing wrong
  with that path specifically — the bug was only in how a *stated*
  postcondition got checked).

## Finding 2: template-shape constraints are stubs — NOT fixed, documented as a limitation

`_accumulator_constraints()`, `_binary_search_constraints()`, and
`_min_max_constraints()` (`z3_verifier.py`) are all empty-list stubs — each
has a comment describing what it should constrain (e.g. "Min/max value should
be from the array") followed by `pass` and `return constraints` on an
untouched empty list.

This means `template_type` (`ACCUMULATOR`, `MIN_MAX_LOOP`, etc., inferred by
each adapter's `infer_template()`) is currently pure classification metadata
— it contributes zero actual Z3 constraints tying the proof to the code's
real structure. Even after Finding 1's fix, this verifier can only check
whether a stated `@ensures` clause is a logical consequence of a stated
`@requires` clause as bare formulas — it has no model of what the loop
actually computes. A postcondition that's true only because of what the loop
body does (not just because of what the precondition literally states) is
not something this verifier can prove, template label or not.

This is a materially weaker guarantee than this project's own already-shipped
`pyprover/loop_verifier.py`, which builds real Hoare-logic INIT and
PRESERVATION proof obligations from the loop's actual AST structure (§2.1 of
this same file for `loop_verifier`'s provenance).

**Conclusion:** the valuable, non-duplicated asset in this archive is the
adapter/parsing layer (`adapters/*.py` — real multi-language `@requires`/
`@ensures`/`@assume` extraction, including genuine `ast`-based parsing for
Python), not the verification core. A real integration should port the
adapters' `extract_contracts()` output (a language-agnostic `Contract`
dataclass) into this project's existing, stronger verification engine rather
than wiring up `verifier.py`/`z3_verifier.py` as bundled here.

## Also noted, not a blocking issue

`ConstraintGenerator.parse_contract_expression()` uses `eval()` with an empty
`__builtins__` dict and a namespace restricted to Z3 objects — meaningfully
reduced attack surface vs. arbitrary `eval()`, but still `eval()`, despite
`test_z3_verifier_fixed.py`'s docstring claiming it works "without unsafe
eval()." This project's own `pyprover/contract_simplifier.py::_expr_to_z3`
already does the equivalent job via `ast.parse()` + a manual node-type
dispatch, with no `eval()` at all — a real integration should prefer reusing
that existing, already-audited approach over porting this one.

## What was and wasn't done this session

- Fixed and re-verified Finding 1 in an isolated sandbox
  (`/home/claude/work/old-versions/pyprover_v11_2_test/`, not part of any
  packaged output — the fix lives in `verifier_SOUNDNESS_FIXED.py` here).
- Did not integrate any of this into `src/pyprover/` — see roadmap.md §12.6
  for why (scope: 6 languages × adapting to `common.interop` types × rewiring
  onto the stronger existing verification core × tests, is a separately-scoped
  task, not a same-session extension of this audit).
