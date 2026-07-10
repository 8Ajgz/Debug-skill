"""PyProver Quantifier Support - forall/exists over Z3

Gap found in a version comparison: PyProver v6.1, v7.0, and an earlier
unversioned phase1-3 build all had some form of quantifier handling
(QuantifierParser/QuantifierProcessor in the phase1-3 build; `forall`
templates referenced but never implemented in FFIContract.to_z3_constraint
in types_phase3.py). Neither this bundled debug-suite fork (v14.1) nor the
standalone pyprover skill (v13.1) had a REAL quantifier implementation --
v13.1's ConstraintGenerator matched `all(...)`/`any(...)` syntax with regex
and threw the quantified condition away, asserting only a structural
"length >= 0 / length >= 1" stand-in (see standalone z3_verifier.py,
Feature #1). This module is a genuine implementation, not a port of either
placeholder.

Supported surface syntax (matches the `all()`/`any()` convention already
used elsewhere in this codebase, so it's consistent rather than inventing a
new spec language):

    all(<cond> for <var> in range(<lo>, <hi>))   -> ForAll
    any(<cond> for <var> in range(<lo>, <hi>))   -> Exists
    all(<cond> for <var> in range(<hi>))         -> lo defaults to 0
    any(<cond> for <var> in range(<hi>))

<cond> is parsed with the same restricted-arithmetic grammar used by
contract_verifier._expr_to_z3 (passed in by the caller, see
`parse_quantifier_clause`), so quantifiers compose with everything that
grammar already supports (+, -, *, //, %, comparisons, and/or/not).

Two verification strategies, chosen automatically:
  1. Native Z3 ForAll/Exists (z3.ForAll / z3.Exists) -- sound, used when the
     bound is symbolic or large. This is what "verified" actually means: a
     real quantifier assertion handed to the solver, not a bounded check
     dressed up as one.
  2. Bounded unroll -- when the range bound is a small integer literal
     (<= MAX_UNROLL, default 64), the quantifier is expanded into a
     conjunction/disjunction of concrete instances instead. This mirrors the
     bounded-unroll approach equivalence_verifier.py already uses for
     `for x in range(N)` loops, so it's consistent with this suite's existing
     philosophy on bounded vs. unbounded checking, and is stated explicitly
     in `QuantifierCheckResult.strategy` rather than left implicit.

Out of scope, and reported as `status="unsupported"` rather than silently
skipped or guessed at: nested quantifiers, quantifying over non-range
collections (e.g. `for x in arr` without a Z3 Array model), and any <cond>
containing constructs contract_verifier's grammar doesn't parse (function
calls, string ops -- see z3_workarounds.py for the latter).
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False

MAX_UNROLL = 64

_QUANT_RE = re.compile(
    r'^(all|any)\(\s*(.+?)\s+for\s+(\w+)\s+in\s+range\(\s*(.+?)\s*\)\s*\)$'
)


@dataclass
class QuantifierClause:
    """A parsed forall/exists clause, prior to Z3 translation."""
    kind: str              # "forall" | "exists"
    bound_var: str
    lo_expr: str
    hi_expr: str
    condition: str


@dataclass
class QuantifierCheckResult:
    verified: bool
    strategy: str                      # "native_z3" | "bounded_unroll" | "unsupported"
    status: str                        # "verified" | "violated" | "unsupported" | "unknown"
    detail: str
    counterexample: Optional[str] = None
    instances_checked: Optional[int] = None


def try_parse_quantifier(expr: str) -> Optional[QuantifierClause]:
    """Parse a clause string as a quantifier; return None if it isn't one.

    This is a syntactic check only -- it does not touch Z3 and never raises.
    """
    if not expr:
        return None
    m = _QUANT_RE.match(expr.strip())
    if not m:
        return None
    kind_word, condition, bound_var, range_args = m.groups()
    kind = "forall" if kind_word == "all" else "exists"

    parts = [p.strip() for p in range_args.split(',')]
    if len(parts) == 1:
        lo_expr, hi_expr = "0", parts[0]
    elif len(parts) == 2:
        lo_expr, hi_expr = parts[0], parts[1]
    else:
        # range(lo, hi, step) -- step isn't supported, refuse to guess
        return None

    return QuantifierClause(
        kind=kind, bound_var=bound_var, lo_expr=lo_expr, hi_expr=hi_expr,
        condition=condition,
    )


def _try_int_literal(expr: str) -> Optional[int]:
    try:
        return int(expr.strip())
    except (ValueError, TypeError):
        return None


def check_quantifier(
    clause: QuantifierClause,
    env: Dict[str, Any],
    expr_to_z3: Callable[[Any, Dict[str, Any]], Any],
    timeout_ms: int = 3000,
) -> QuantifierCheckResult:
    """Verify a quantifier clause is satisfiable under the given environment.

    `expr_to_z3` is the caller's own AST->Z3 expression translator (e.g.
    contract_verifier._expr_to_z3), passed in rather than imported, so this
    module has no import-cycle dependency on any specific verifier file --
    every call site in this codebase already defines its own local
    `_expr_to_z3` (see the module docstring in contract_verifier.py for why),
    and this module respects that pattern instead of trying to unify it.

    Checks satisfiability of the quantified statement, not implication from
    a separate set of preconditions -- callers that need
    "preconditions imply this quantifier" should conjoin their precondition
    Z3 exprs with the result of this function's underlying assertion
    themselves (this mirrors how contract_verifier.py's own
    `_check_satisfiable` / `_check_implied` split works).
    """
    if not Z3_AVAILABLE:
        return QuantifierCheckResult(
            verified=False, strategy="unsupported", status="unsupported",
            detail="z3 not installed",
        )

    import ast

    lo_lit = _try_int_literal(clause.lo_expr)
    hi_lit = _try_int_literal(clause.hi_expr)

    # Strategy 1: bounded unroll, when both bounds are small integer literals.
    if lo_lit is not None and hi_lit is not None and (hi_lit - lo_lit) <= MAX_UNROLL:
        instances = []
        for i in range(lo_lit, hi_lit):
            local_env = dict(env)
            local_env[clause.bound_var] = i  # concrete Python int, not a Z3 var
            try:
                tree = ast.parse(_substitute_literal(clause.condition, clause.bound_var, i), mode="eval")
                z3_expr = expr_to_z3(tree.body, local_env)
            except Exception as e:
                return QuantifierCheckResult(
                    verified=False, strategy="bounded_unroll", status="unsupported",
                    detail=f"could not parse condition at {clause.bound_var}={i}: {e}",
                )
            if z3_expr is None:
                return QuantifierCheckResult(
                    verified=False, strategy="bounded_unroll", status="unsupported",
                    detail=f"condition did not translate to Z3 at {clause.bound_var}={i}",
                )
            instances.append(z3_expr)

        if not instances:
            return QuantifierCheckResult(
                verified=True, strategy="bounded_unroll", status="verified",
                detail="empty range -- vacuously true", instances_checked=0,
            )

        # Check each instance individually (rather than one big And/Or query)
        # specifically so a violation can be reported against the concrete
        # bound_var value that failed -- a single combined query's model has
        # no free variables to read back (every instance is a closed formula
        # by this point), which is a real gap: an empty counterexample string
        # is worse than no field at all, so it isn't shipped that way here.
        solver = z3.Solver()
        solver.set("timeout", timeout_ms)
        if clause.kind == "forall":
            for i, inst in zip(range(lo_lit, hi_lit), instances):
                solver.push()
                solver.add(z3.Not(inst))
                r = solver.check()
                solver.pop()
                if r == z3.sat:
                    return QuantifierCheckResult(
                        verified=False, strategy="bounded_unroll", status="violated",
                        detail=f"forall violated at {clause.bound_var}={i}",
                        counterexample=f"{clause.bound_var} = {i}",
                        instances_checked=len(instances),
                    )
                elif r == z3.unknown:
                    return QuantifierCheckResult(
                        verified=False, strategy="bounded_unroll", status="unknown",
                        detail=f"solver timeout at {clause.bound_var}={i}",
                        instances_checked=len(instances),
                    )
            return QuantifierCheckResult(
                verified=True, strategy="bounded_unroll", status="verified",
                detail=f"checked {len(instances)} concrete instance(s), all consistent",
                instances_checked=len(instances),
            )
        else:  # exists
            for i, inst in zip(range(lo_lit, hi_lit), instances):
                solver.push()
                solver.add(inst)
                r = solver.check()
                solver.pop()
                if r == z3.sat:
                    return QuantifierCheckResult(
                        verified=True, strategy="bounded_unroll", status="verified",
                        detail=f"exists satisfied at {clause.bound_var}={i}",
                        counterexample=f"{clause.bound_var} = {i}",
                        instances_checked=len(instances),
                    )
            return QuantifierCheckResult(
                verified=False, strategy="bounded_unroll", status="violated",
                detail=f"no instance in range satisfies the condition "
                       f"(checked {len(instances)})",
                instances_checked=len(instances),
            )

    # Strategy 2: native Z3 quantifier, for symbolic or large bounds.
    try:
        bound_z3 = z3.Int(clause.bound_var)
        local_env = dict(env)
        local_env[clause.bound_var] = bound_z3
        tree = ast.parse(clause.condition, mode="eval")
        cond_z3 = expr_to_z3(tree.body, local_env)
        if cond_z3 is None:
            return QuantifierCheckResult(
                verified=False, strategy="unsupported", status="unsupported",
                detail="condition did not translate to Z3",
            )
        lo_tree = ast.parse(clause.lo_expr, mode="eval")
        hi_tree = ast.parse(clause.hi_expr, mode="eval")
        lo_z3 = expr_to_z3(lo_tree.body, env)
        hi_z3 = expr_to_z3(hi_tree.body, env)
        if lo_z3 is None or hi_z3 is None:
            return QuantifierCheckResult(
                verified=False, strategy="unsupported", status="unsupported",
                detail="range bound did not translate to Z3",
            )
        in_range = z3.And(bound_z3 >= lo_z3, bound_z3 < hi_z3)
        body = z3.Implies(in_range, cond_z3) if clause.kind == "forall" else z3.And(in_range, cond_z3)
        quantified = z3.ForAll([bound_z3], body) if clause.kind == "forall" else z3.Exists([bound_z3], body)

        solver = z3.Solver()
        solver.set("timeout", timeout_ms)
        solver.add(z3.Not(quantified))
        r = solver.check()
        if r == z3.unsat:
            return QuantifierCheckResult(
                verified=True, strategy="native_z3", status="verified",
                detail=f"{clause.kind} holds (proved via native Z3 quantifier)",
            )
        elif r == z3.sat:
            return QuantifierCheckResult(
                verified=False, strategy="native_z3", status="violated",
                detail=f"{clause.kind} does not hold (Z3 found a violation, "
                       f"model over quantified variable not extractable directly)",
            )
        else:
            return QuantifierCheckResult(
                verified=False, strategy="native_z3", status="unknown",
                detail="solver timeout or undecidable fragment "
                       "(quantifier reasoning is undecidable in general -- "
                       "Z3 uses incomplete heuristics for quantified formulas)",
            )
    except Exception as e:
        return QuantifierCheckResult(
            verified=False, strategy="unsupported", status="unsupported",
            detail=f"quantifier translation failed: {e}",
        )


def _substitute_literal(condition: str, var: str, value: int) -> str:
    """Textually substitute a bound variable with a concrete int literal.

    Used only for the bounded-unroll path, where each instance needs its own
    concrete value baked into the expression string before re-parsing. Uses a
    word-boundary regex rather than str.replace to avoid corrupting longer
    identifiers that happen to contain `var` as a substring.
    """
    return re.sub(rf'\b{re.escape(var)}\b', f'({value})', condition)


__all__ = [
    'QuantifierClause', 'QuantifierCheckResult',
    'try_parse_quantifier', 'check_quantifier', 'MAX_UNROLL',
]
