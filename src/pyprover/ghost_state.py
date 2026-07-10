"""PyProver Ghost State Tracking

Gap found in a version comparison: an earlier unversioned phase1-3 PyProver
build had GhostStateTracker / GhostVariable / GhostUpdate, but that
implementation only ever appended free-text "update" strings to a list and
returned them unmodified from `reconstruct_ghost_state` -- there was no Z3
involvement and no check that the tracked value was ever consistent with
anything. This module keeps the concept (spec-only auxiliary variables that
exist purely to make a loop/function's specification expressible, with no
runtime effect on the actual code) but backs it with real Z3 constraints,
consistent with how the rest of this fork treats "verification": a ghost
variable's declared relationship to real variables is checked, not just
recorded.

What a ghost variable is, for readers unfamiliar with the term (borrowed
from ACSL/Dafny/Why3): a variable that appears only in specifications
(invariants, postconditions), never in the actual executable code. It lets
you specify things like "the number of elements processed so far" or "the
running maximum seen" even when the real code doesn't keep an explicit
variable for that -- useful for loop invariants over implicit state.

Extraction convention (consistent with contract_verifier.py's
`# Pre:`/`# Post:`/`# Inv:` comment scanning):

    # Ghost: <name> = <initial_expr>
    # GhostUpdate: <name> = <expr_in_terms_of_other_vars_and_previous_name>

Both lines are plain Z3-arithmetic expressions using the same restricted
grammar as contract_verifier._expr_to_z3 (passed in by the caller).

Scope, stated honestly: this checks that a *sequence* of declared ghost
updates is jointly satisfiable with a given set of real-variable
constraints (e.g. "does the ghost accumulator staying non-negative remain
consistent with the loop's actual increment constraint") -- it does not
execute the ghost update symbolically across an unbounded number of loop
iterations. For that, wrap the ghost variable in a `# Inv:` clause and use
the existing loop_verifier.py INIT/PRESERVATION machinery instead; ghost
variables declared here are meant to be referenced from such invariants,
not to replace them.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False

_GHOST_DECL_RE = re.compile(r'(?:#|//)\s*Ghost:\s*(\w+)\s*=\s*(.+)$')
_GHOST_UPDATE_RE = re.compile(r'(?:#|//)\s*GhostUpdate:\s*(\w+)\s*=\s*(.+)$')


@dataclass
class GhostVariable:
    """A single spec-only variable and its declared initial value expression."""
    name: str
    initial_expr: str
    line_number: Optional[int] = None


@dataclass
class GhostUpdate:
    """A declared update to a ghost variable's value."""
    name: str
    update_expr: str
    line_number: Optional[int] = None


@dataclass
class GhostStateResult:
    consistent: bool
    status: str                # "verified" | "inconsistent" | "unsupported"
    detail: str
    counterexample: Optional[str] = None


class GhostStateTracker:
    """Extract and Z3-check ghost variable declarations from source comments."""

    @staticmethod
    def extract(source_code: str) -> "tuple[List[GhostVariable], List[GhostUpdate]]":
        """Scan source for `# Ghost:` and `# GhostUpdate:` comment annotations."""
        declarations: List[GhostVariable] = []
        updates: List[GhostUpdate] = []
        for i, line in enumerate(source_code.split('\n'), start=1):
            m = _GHOST_DECL_RE.search(line)
            if m:
                declarations.append(GhostVariable(
                    name=m.group(1), initial_expr=m.group(2).strip(), line_number=i,
                ))
                continue
            m = _GHOST_UPDATE_RE.search(line)
            if m:
                updates.append(GhostUpdate(
                    name=m.group(1), update_expr=m.group(2).strip(), line_number=i,
                ))
        return declarations, updates

    @staticmethod
    def check_consistency(
        declarations: List[GhostVariable],
        updates: List[GhostUpdate],
        real_var_env: Dict[str, Any],
        expr_to_z3: Callable[[Any, Dict[str, Any]], Any],
        real_var_constraints: Optional[List[Any]] = None,
        timeout_ms: int = 3000,
    ) -> GhostStateResult:
        """Check that declared ghost variables and their updates are jointly
        satisfiable alongside a set of real-variable Z3 constraints.

        `real_var_env` should already contain the Z3 variables for the
        function's actual parameters/locals (built the same way callers
        already build environments for contract_verifier/loop_verifier), so
        ghost expressions that reference real variables resolve correctly.

        `real_var_constraints` is the list of actual Z3 boolean constraints
        on those variables (e.g. parsed `# Pre:` clauses) -- pass these in
        explicitly if you want "jointly satisfiable with the real
        constraints" to mean something. Without them, this only checks the
        ghost declarations/updates for self-consistency, which is a real but
        much weaker guarantee; that weaker mode is still reported honestly
        via `detail`, not silently upgraded to the stronger claim.

        `expr_to_z3` is the caller's own AST->Z3 translator, passed in for
        the same reason quantifiers.py takes one -- no cross-file import
        coupling to a specific verifier's local `_expr_to_z3`.
        """
        if not Z3_AVAILABLE:
            return GhostStateResult(
                consistent=False, status="unsupported", detail="z3 not installed",
            )
        if not declarations and not updates:
            return GhostStateResult(
                consistent=True, status="verified", detail="no ghost variables declared",
            )

        import ast

        env = dict(real_var_env)
        solver = z3.Solver()
        solver.set("timeout", timeout_ms)
        for c in (real_var_constraints or []):
            solver.add(c)

        for decl in declarations:
            ghost_var = z3.Int(decl.name)
            env[decl.name] = ghost_var
            try:
                tree = ast.parse(decl.initial_expr, mode="eval")
                init_z3 = expr_to_z3(tree.body, env)
            except Exception as e:
                return GhostStateResult(
                    consistent=False, status="unsupported",
                    detail=f"ghost '{decl.name}' initial expression did not parse: {e}",
                )
            if init_z3 is None:
                return GhostStateResult(
                    consistent=False, status="unsupported",
                    detail=f"ghost '{decl.name}' initial expression did not translate to Z3",
                )
            solver.add(ghost_var == init_z3)

        for upd in updates:
            if upd.name not in env:
                return GhostStateResult(
                    consistent=False, status="unsupported",
                    detail=f"GhostUpdate references undeclared ghost variable '{upd.name}' "
                           f"(add a matching '# Ghost: {upd.name} = ...' declaration first)",
                )
            try:
                tree = ast.parse(upd.update_expr, mode="eval")
                update_z3 = expr_to_z3(tree.body, env)
            except Exception as e:
                return GhostStateResult(
                    consistent=False, status="unsupported",
                    detail=f"ghost update for '{upd.name}' did not parse: {e}",
                )
            if update_z3 is None:
                return GhostStateResult(
                    consistent=False, status="unsupported",
                    detail=f"ghost update for '{upd.name}' did not translate to Z3",
                )
            # Model the update as a fresh SSA-style variable so a sequence of
            # updates to the same name doesn't silently self-contradict via
            # reusing one Z3 constant across two different assigned values.
            new_var = z3.Int(f"{upd.name}__upd{upd.line_number}")
            solver.add(new_var == update_z3)
            env[upd.name] = new_var

        r = solver.check()
        if r == z3.sat:
            scope = (
                f"jointly satisfiable with {len(real_var_constraints)} real-variable constraint(s)"
                if real_var_constraints else
                "self-consistent (no real-variable constraints were supplied to check against)"
            )
            return GhostStateResult(
                consistent=True, status="verified",
                detail=f"{len(declarations)} ghost variable(s), {len(updates)} update(s): {scope}",
            )
        elif r == z3.unsat:
            try:
                core = solver.unsat_core()
            except Exception:
                core = None
            return GhostStateResult(
                consistent=False, status="inconsistent",
                detail="ghost state declarations/updates are contradictory "
                       "with each other or with the real-variable constraints",
                counterexample=str(core) if core else None,
            )
        else:
            return GhostStateResult(
                consistent=False, status="unsupported", detail="solver timeout",
            )


__all__ = [
    'GhostVariable', 'GhostUpdate', 'GhostStateResult', 'GhostStateTracker',
]
