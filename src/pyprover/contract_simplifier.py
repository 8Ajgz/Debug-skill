"""PyProver Contract Simplifier

Iterative Z3 implication-check removal of redundant @requires/@ensures clauses,
producing a minimal equivalent contract.

WHAT THIS OPERATES ON: a contract specification (two lists of clause strings —
the text already extracted from `# Pre:`/`# Post:` annotations elsewhere), not
code. simplify() never sees a function body. If you're looking for "prove code
A can be rewritten as code B and still produce the same result" - that is a
DIFFERENT, NOT-YET-BUILT capability. This module only removes clauses from a
contract that are already logically implied by the *other clauses in that same
contract* - it says nothing about whether the underlying code actually
satisfies any of them (that's ContractVerifier's job, on the unsimplified or
simplified spec either way).

What counts as redundant:
  - A requires-clause that is implied by the conjunction of all other requires-clauses
    (e.g. "n >= 0" when "n >= 0 and n < 10" is also a precondition)
  - An ensures-clause that is implied by the preconditions plus the other ensures-clauses
  - A tautology ("True", "n == n")
  - Two clauses that are logically equivalent under integer semantics
    (e.g. "x > 0" and "x >= 1" — the latter implies the former when x is an int)

Soundness guarantee: clauses that Z3 cannot decide within the timeout are KEPT,
never silently dropped. This is a soundness-preserving simplifier.

Integration: the ContractVerifier.parse_contract() in contract_verifier.py extracts
clauses; ContractSimplifier then reduces them. Wire together via simplify_parsed_contract().
"""

import ast
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False

from . import z3_builtins
from .contract_verifier import _conditional_parts, _expr_to_z3, seed_real_env


# ---------------------------------------------------------------------------
# Data classes (from recovered fragment, now with complete implementations)
# ---------------------------------------------------------------------------

@dataclass
class RemovedClause:
    """A clause removed during simplification, with a reason."""
    clause: str
    kind: str           # 'requires' or 'ensures'
    reason: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.clause!r} — {self.reason}"


@dataclass
class ContractSimplificationResult:
    """Result of contract simplification."""
    original_requires: List[str]
    original_ensures: List[str]
    simplified_requires: List[str]
    simplified_ensures: List[str]
    removed: List[RemovedClause] = field(default_factory=list)
    timeout_clauses: List[str] = field(default_factory=list)
    unsupported_clauses: List[str] = field(default_factory=list)
    z3_available: bool = True

    @property
    def reduction_count(self) -> int:
        return len(self.removed)

    @property
    def original_count(self) -> int:
        return len(self.original_requires) + len(self.original_ensures)

    @property
    def simplified_count(self) -> int:
        return len(self.simplified_requires) + len(self.simplified_ensures)

    @property
    def reduction_pct(self) -> float:
        if self.original_count == 0:
            return 0.0
        return self.reduction_count / self.original_count * 100

    def as_decorators(self) -> str:
        """Return the simplified contract as Python decorator strings."""
        lines = []
        # json.dumps quotes the clause as a valid Python string literal, so a
        # clause containing double quotes (e.g. s == "a") stays parseable.
        for clause in self.simplified_requires:
            lines.append(f"@requires({json.dumps(clause)})")
        for clause in self.simplified_ensures:
            lines.append(f"@ensures({json.dumps(clause)})")
        return "\n".join(lines) if lines else "# No contracts required"

    def summary(self) -> str:
        """Return a human-readable simplification report."""
        if not self.z3_available:
            return "Z3 not available — install z3-solver to enable contract simplification"
        if self.original_count == 0:
            return "No contract clauses found to simplify."
        lines = [
            f"Contract Simplification: "
            f"{self.original_count} → {self.simplified_count} clauses "
            f"({self.reduction_pct:.0f}% reduction)"
        ]
        if self.removed:
            lines.append("Removed clauses:")
            for r in self.removed:
                lines.append(f"  {r}")
        if self.timeout_clauses:
            lines.append("Kept (Z3 timeout, conservative):")
            for c in self.timeout_clauses:
                lines.append(f"  {c!r}")
        if self.unsupported_clauses:
            lines.append("Kept (not expressible in Z3, not checked):")
            for c in self.unsupported_clauses:
                lines.append(f"  {c!r}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Z3 expression parsing (reuse the same approach as loop_verifier)
# ---------------------------------------------------------------------------



def _clause_to_z3(clause_str: str, env: Dict[str, Any]) -> Optional[Any]:
    """Parse a clause string to Z3; return None if unsupported."""
    try:
        parts = _conditional_parts(clause_str)
        if parts is not None:  # "if cond: clause" -> Implies(cond, clause), as in contract_verifier
            cond = _expr_to_z3(parts[0], env)
            then = _expr_to_z3(parts[1], env)
            if _is_z3_bool(cond) and _is_z3_bool(then):
                return z3.Implies(cond, then)
            return None
        tree = ast.parse(clause_str, mode="eval")
        return _expr_to_z3(tree.body, env)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core implication check
# ---------------------------------------------------------------------------

def _is_z3_bool(expr: Any) -> bool:
    """True if expr is a Z3 Boolean-sorted expression (safe to Solver.add()/Not()).

    A bare identifier clause (e.g. an ensures-clause of just "result", no
    comparison) parses via `_expr_to_z3`'s `ast.Name` branch to a Z3 Int,
    not a predicate. z3.Not() and Solver.add() both raise Z3Exception on a
    non-Bool sort, so any call site that might receive a bare-identifier
    clause must check this first.
    """
    try:
        return expr.sort_kind() == z3.Z3_BOOL_SORT
    except Exception:
        return False


def _implies(antecedent_clauses: List[Any], consequent: Any, timeout_ms: int) -> str:
    """Check if ∧(antecedent_clauses) → consequent.

    Returns: 'yes' (implied), 'no' (not implied), 'unknown' (timeout/error).
    A non-boolean consequent (see `_is_z3_bool`) can't be checked and
    returns 'unknown' so the caller conservatively keeps the clause rather
    than crashing or silently dropping it.
    """
    if not _is_z3_bool(consequent):
        return "unknown"
    s = z3.Solver()
    s.set("timeout", timeout_ms)
    if antecedent_clauses:
        antecedent_clauses = [c for c in antecedent_clauses if _is_z3_bool(c)]
        if antecedent_clauses:
            s.add(z3.And(*antecedent_clauses))
    s.add(z3.Not(consequent))
    r = s.check()
    if r == z3.unsat:
        return "yes"   # ¬consequent is unsatisfiable given antecedents → it's implied
    if r == z3.sat:
        return "no"
    return "unknown"


def _is_tautology(expr: Any, timeout_ms: int) -> bool:
    """Return True if expr is always True (Z3 proves ¬expr UNSAT).

    A non-boolean expr (see `_is_z3_bool`) is never a tautology in the
    predicate sense — return False rather than crashing.
    """
    if not _is_z3_bool(expr):
        return False
    s = z3.Solver()
    s.set("timeout", timeout_ms)
    s.add(z3.Not(expr))
    return s.check() == z3.unsat


# ---------------------------------------------------------------------------
# ContractSimplifier
# ---------------------------------------------------------------------------

class ContractSimplifier:
    """Iterative Z3-based redundant clause elimination.

    Usage::

        simplifier = ContractSimplifier()
        result = simplifier.simplify(
            requires=["n >= 0", "n >= 0 and n < 10"],
            ensures=["result >= 0"],
        )
        print(result.summary())
        print(result.as_decorators())
    """

    def __init__(self, timeout_ms: int = 3000):
        self.timeout_ms = timeout_ms

    def simplify(
        self,
        requires: List[str],
        ensures: List[str],
    ) -> ContractSimplificationResult:
        """Simplify a contract to a minimal equivalent set.

        A requires-clause is redundant if the other requires-clauses already
        imply it. An ensures-clause is redundant if the requires-clauses plus
        the other ensures-clauses imply it.
        """
        result = ContractSimplificationResult(
            original_requires=list(requires),
            original_ensures=list(ensures),
            simplified_requires=list(requires),
            simplified_ensures=list(ensures),
            z3_available=Z3_AVAILABLE,
        )

        if not Z3_AVAILABLE:
            return result

        env: Dict[str, Any] = {}
        seed_real_env(requires + ensures, env)
        z3_builtins.seed_string_env(requires + ensures, env)

        # Parse all clauses up front. Work on indices, not clause strings, so
        # that duplicate clauses are separate entries and can be collapsed.
        parsed_req = [_clause_to_z3(c, env) for c in requires]
        parsed_ens = [_clause_to_z3(c, env) for c in ensures]

        # --- Simplify requires ---
        active_req = list(range(len(requires)))

        for i in list(active_req):
            clause = requires[i]
            z3_clause = parsed_req[i]
            if z3_clause is None or not _is_z3_bool(z3_clause):
                result.unsupported_clauses.append(clause)   # keep, cannot check
                continue

            # Tautology check first
            if _is_tautology(z3_clause, self.timeout_ms):
                active_req.remove(i)
                result.removed.append(RemovedClause(
                    clause=clause,
                    kind="requires",
                    reason="Tautology (always true)",
                ))
                continue

            # Implication check: do the remaining requires imply this clause?
            others = [parsed_req[j] for j in active_req if j != i and parsed_req[j] is not None]
            if not others:
                continue
            r = _implies(others, z3_clause, self.timeout_ms)
            if r == "yes":
                active_req.remove(i)
                result.removed.append(RemovedClause(
                    clause=clause,
                    kind="requires",
                    reason="Implied by the remaining preconditions",
                ))
            elif r == "unknown":
                result.timeout_clauses.append(clause)

        result.simplified_requires = [requires[i] for i in active_req]

        # --- Simplify ensures ---
        active_ens = list(range(len(ensures)))

        # Gather the (now-simplified) requires as antecedents for ensures checks
        req_z3 = [parsed_req[i] for i in active_req if parsed_req[i] is not None]

        for i in list(active_ens):
            clause = ensures[i]
            z3_clause = parsed_ens[i]
            if z3_clause is None or not _is_z3_bool(z3_clause):
                result.unsupported_clauses.append(clause)
                continue

            if _is_tautology(z3_clause, self.timeout_ms):
                active_ens.remove(i)
                result.removed.append(RemovedClause(
                    clause=clause,
                    kind="ensures",
                    reason="Tautology (always true)",
                ))
                continue

            # Antecedents: all requires + other ensures
            other_ens = [parsed_ens[j] for j in active_ens if j != i and parsed_ens[j] is not None]
            antecedents = req_z3 + other_ens
            if not antecedents:
                continue
            r = _implies(antecedents, z3_clause, self.timeout_ms)
            if r == "yes":
                active_ens.remove(i)
                result.removed.append(RemovedClause(
                    clause=clause,
                    kind="ensures",
                    reason="Implied by preconditions and remaining postconditions",
                ))
            elif r == "unknown":
                result.timeout_clauses.append(clause)

        result.simplified_ensures = [ensures[i] for i in active_ens]
        return result


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def simplify_parsed_contract(
    requires: List[str],
    ensures: List[str],
    timeout_ms: int = 3000,
) -> ContractSimplificationResult:
    """Simplify a contract given lists of requires/ensures clause strings."""
    return ContractSimplifier(timeout_ms=timeout_ms).simplify(requires, ensures)
