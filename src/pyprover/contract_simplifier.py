"""PyProver Contract Simplifier

Iterative Z3 implication-check removal of redundant @requires/@ensures clauses,
producing a minimal equivalent contract.

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
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False


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
        for clause in self.simplified_requires:
            lines.append(f'@requires("{clause}")')
        for clause in self.simplified_ensures:
            lines.append(f'@ensures("{clause}")')
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
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Z3 expression parsing (reuse the same approach as loop_verifier)
# ---------------------------------------------------------------------------

_OP_MAP = {
    ast.Add:    lambda a, b: a + b,
    ast.Sub:    lambda a, b: a - b,
    ast.Mult:   lambda a, b: a * b,
    ast.FloorDiv: lambda a, b: a / b,
    ast.Div:    lambda a, b: a / b,
    ast.Mod:    lambda a, b: a % b,
    ast.Lt:     lambda a, b: a < b,
    ast.LtE:    lambda a, b: a <= b,
    ast.Gt:     lambda a, b: a > b,
    ast.GtE:    lambda a, b: a >= b,
    ast.Eq:     lambda a, b: a == b,
    ast.NotEq:  lambda a, b: a != b,
}


def _expr_to_z3(node: ast.expr, env: Dict[str, Any]) -> Any:
    """Recursively convert ast.expr into a Z3 expression."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return z3.BoolVal(node.value)
        return node.value
    if isinstance(node, ast.Name):
        if node.id == "True":
            return z3.BoolVal(True)
        if node.id == "False":
            return z3.BoolVal(False)
        if node.id not in env:
            env[node.id] = z3.Int(node.id)
        return env[node.id]
    if isinstance(node, ast.BinOp):
        left = _expr_to_z3(node.left, env)
        right = _expr_to_z3(node.right, env)
        op = _OP_MAP.get(type(node.op))
        if op is None:
            raise NotImplementedError(f"Unsupported BinOp: {type(node.op).__name__}")
        return op(left, right)
    if isinstance(node, ast.BoolOp):
        values = [_expr_to_z3(v, env) for v in node.values]
        if isinstance(node.op, ast.And):
            return z3.And(*values)
        return z3.Or(*values)
    if isinstance(node, ast.UnaryOp):
        operand = _expr_to_z3(node.operand, env)
        if isinstance(node.op, ast.Not):
            return z3.Not(operand)
        if isinstance(node.op, ast.USub):
            return -operand
        raise NotImplementedError(f"Unsupported UnaryOp: {type(node.op).__name__}")
    if isinstance(node, ast.Compare):
        left = _expr_to_z3(node.left, env)
        result = None
        for op, comparator in zip(node.ops, node.comparators):
            right = _expr_to_z3(comparator, env)
            cmp = _OP_MAP.get(type(op))
            if cmp is None:
                raise NotImplementedError(f"Unsupported Compare: {type(op).__name__}")
            part = cmp(left, right)
            result = part if result is None else z3.And(result, part)
            left = right
        return result
    raise NotImplementedError(f"Unsupported node type: {type(node).__name__}")


def _clause_to_z3(clause_str: str, env: Dict[str, Any]) -> Optional[Any]:
    """Parse a clause string to Z3; return None if unsupported."""
    try:
        tree = ast.parse(clause_str, mode="eval")
        return _expr_to_z3(tree.body, env)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core implication check
# ---------------------------------------------------------------------------

def _implies(antecedent_clauses: List[Any], consequent: Any, timeout_ms: int) -> str:
    """Check if ∧(antecedent_clauses) → consequent.

    Returns: 'yes' (implied), 'no' (not implied), 'unknown' (timeout/error).
    """
    s = z3.Solver()
    s.set("timeout", timeout_ms)
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
    """Return True if expr is always True (Z3 proves ¬expr UNSAT)."""
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

        # Parse all clauses up front — unparseable ones are kept automatically
        parsed_req = {c: _clause_to_z3(c, env) for c in requires}
        parsed_ens = {c: _clause_to_z3(c, env) for c in ensures}

        # --- Simplify requires ---
        active_req = list(requires)
        removed_req: List[str] = []

        for clause in list(active_req):
            z3_clause = parsed_req.get(clause)
            if z3_clause is None:
                continue   # keep unparseable

            # Tautology check first
            if _is_tautology(z3_clause, self.timeout_ms):
                active_req.remove(clause)
                removed_req.append(clause)
                result.removed.append(RemovedClause(
                    clause=clause,
                    kind="requires",
                    reason="Tautology (always true)",
                ))
                continue

            # Implication check: do the remaining requires imply this clause?
            others = [parsed_req[c] for c in active_req if c != clause and parsed_req.get(c) is not None]
            if not others:
                continue
            r = _implies(others, z3_clause, self.timeout_ms)
            if r == "yes":
                active_req.remove(clause)
                removed_req.append(clause)
                result.removed.append(RemovedClause(
                    clause=clause,
                    kind="requires",
                    reason="Implied by the remaining preconditions",
                ))
            elif r == "unknown":
                result.timeout_clauses.append(clause)

        result.simplified_requires = active_req

        # --- Simplify ensures ---
        active_ens = list(ensures)

        # Gather the (now-simplified) requires as antecedents for ensures checks
        req_z3 = [parsed_req[c] for c in active_req if parsed_req.get(c) is not None]

        for clause in list(active_ens):
            z3_clause = parsed_ens.get(clause)
            if z3_clause is None:
                continue

            if _is_tautology(z3_clause, self.timeout_ms):
                active_ens.remove(clause)
                result.removed.append(RemovedClause(
                    clause=clause,
                    kind="ensures",
                    reason="Tautology (always true)",
                ))
                continue

            # Antecedents: all requires + other ensures
            other_ens = [parsed_ens[c] for c in active_ens if c != clause and parsed_ens.get(c) is not None]
            antecedents = req_z3 + other_ens
            if not antecedents:
                continue
            r = _implies(antecedents, z3_clause, self.timeout_ms)
            if r == "yes":
                active_ens.remove(clause)
                result.removed.append(RemovedClause(
                    clause=clause,
                    kind="ensures",
                    reason="Implied by preconditions and remaining postconditions",
                ))
            elif r == "unknown":
                result.timeout_clauses.append(clause)

        result.simplified_ensures = active_ens
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
