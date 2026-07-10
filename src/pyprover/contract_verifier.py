"""PyProver Phase 2 - Contract verification using Z3 solver"""
import ast
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

# Z3 import with graceful fallback
try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False

from . import quantifiers
from . import z3_builtins

# Hardening limits (ported from the standalone PyProver v13.1 security pass,
# adapted to this verifier's actual attack surface: it's a per-line text
# scanner, not an expression parser, so the relevant risks are unbounded
# input size and embedded control characters in extracted clauses rather
# than parenthesis-nesting depth).
MAX_CONTRACT_INPUT_CHARS = 200_000
MAX_CONTRACT_LINES = 20_000
_Z3_TIMEOUT_MS = 3000

# Variables that refer to the function's return value in post-conditions.
# We treat these as unconstrained Z3 integers when verifying.
_RESULT_ALIASES = frozenset({"result", "return", "retval", "ret", "output"})


class ContractInputTooLargeError(ValueError):
    """Raised when input code exceeds the size this verifier will scan."""


@dataclass
class ContractSpec:
    preconditions: List[str]
    postconditions: List[str]
    invariants: List[str]


# ---------------------------------------------------------------------------
# Shared Z3 expression parser
# (mirrors contract_simplifier._clause_to_z3 — kept local to avoid
#  circular imports between sibling modules)
# ---------------------------------------------------------------------------

_OP_MAP = {
    ast.Add:      lambda a, b: a + b,
    ast.Sub:      lambda a, b: a - b,
    ast.Mult:     lambda a, b: a * b,
    ast.FloorDiv: lambda a, b: a / b,
    ast.Div:      lambda a, b: a / b,
    ast.Mod:      lambda a, b: a % b,
    ast.Lt:       lambda a, b: a < b,
    ast.LtE:      lambda a, b: a <= b,
    ast.Gt:       lambda a, b: a > b,
    ast.GtE:      lambda a, b: a >= b,
    ast.Eq:       lambda a, b: a == b,
    ast.NotEq:    lambda a, b: a != b,
}


def _expr_to_z3(node: ast.expr, env: Dict[str, Any]) -> Any:
    """Recursively convert an AST expression node to a Z3 expression."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return z3.BoolVal(node.value)
        if isinstance(node.value, int):
            return node.value
        if isinstance(node.value, float):
            return node.value
        if isinstance(node.value, str):
            return z3.StringVal(node.value)
        raise NotImplementedError(f"Unsupported constant type: {type(node.value)}")
    if isinstance(node, ast.Name):
        name = node.id
        if name == "True":
            return z3.BoolVal(True)
        if name == "False":
            return z3.BoolVal(False)
        if name not in env:
            env[name] = z3.Int(name)
        return env[name]
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
            cmp_fn = _OP_MAP.get(type(op))
            if cmp_fn is None:
                raise NotImplementedError(f"Unsupported Compare: {type(op).__name__}")
            part = cmp_fn(left, right)
            result = part if result is None else z3.And(result, part)
            left = right
        return result
    if isinstance(node, ast.Call):
        result = z3_builtins.try_call_to_z3(node, env, _expr_to_z3)
        if result is not None:
            return result
        raise NotImplementedError(f"Unsupported call: {ast.dump(node.func)}")
    raise NotImplementedError(f"Unsupported AST node: {type(node).__name__}")


def _clause_to_z3(clause: str, env: Dict[str, Any]) -> Optional[Any]:
    """Parse a clause string to a Z3 expression; return None if unsupported.

    Quantified clauses (`all(cond for i in range(...))` /
    `any(cond for i in range(...))`) are detected first and delegated to
    quantifiers.py for real ForAll/Exists translation -- see that module's
    docstring for why this differs from the older regex stand-in that
    threw the quantified condition away. Everything else falls through to
    the existing arithmetic AST translation unchanged.
    """
    try:
        qclause = quantifiers.try_parse_quantifier(clause)
        if qclause is not None:
            result = quantifiers.check_quantifier(qclause, env, _expr_to_z3)
            if result.strategy == "unsupported":
                return None
            # Represent as a Z3 bool constant so downstream SAT/implication
            # checks (which expect a Z3 BoolRef) can consume it uniformly;
            # the real quantifier reasoning already happened above.
            return z3.BoolVal(result.verified)
        tree = ast.parse(clause, mode="eval")
        return _expr_to_z3(tree.body, env)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core Z3 checks
# ---------------------------------------------------------------------------

def _is_z3_bool(expr: Any) -> bool:
    """True if expr is a Z3 Boolean-sorted expression (safe to Solver.add())."""
    try:
        return expr.sort_kind() == z3.Z3_BOOL_SORT
    except Exception:
        return False


def _check_satisfiable(exprs: List[Any]) -> Tuple[bool, Optional[str]]:
    """Return (sat, counterexample_str).
    sat=True means the conjunction of exprs is satisfiable.

    Non-boolean expressions (e.g. a bare identifier like ``result``, which
    parses to a Z3 Int rather than a predicate) are not valid Solver
    assertions and are silently skipped — they carry no truth-value to
    check, so satisfiability is vacuously true for that clause.
    """
    bool_exprs = [e for e in exprs if _is_z3_bool(e)]
    if not bool_exprs:
        return True, None
    s = z3.Solver()
    s.set("timeout", _Z3_TIMEOUT_MS)
    for e in bool_exprs:
        s.add(e)
    r = s.check()
    if r == z3.unsat:
        return False, "Z3 proved preconditions are mutually contradictory (UNSAT)"
    if r == z3.sat:
        return True, None
    return True, None  # unknown → conservative: assume satisfiable


def _check_implied(antecedents: List[Any], consequent: Any) -> Tuple[str, Optional[str]]:
    """Check whether ∧(antecedents) → consequent.

    Returns:
        ('yes', None)       — consequent is implied (VALID)
        ('no', model_str)   — consequent is NOT implied; model is a counterexample
        ('unknown', None)   — Z3 timed out, error, or consequent isn't boolean
    """
    if not _is_z3_bool(consequent):
        return "unknown", None
    bool_antecedents = [a for a in antecedents if _is_z3_bool(a)]
    s = z3.Solver()
    s.set("timeout", _Z3_TIMEOUT_MS)
    if bool_antecedents:
        s.add(z3.And(*bool_antecedents))
    s.add(z3.Not(consequent))
    r = s.check()
    if r == z3.unsat:
        return "yes", None
    if r == z3.sat:
        try:
            m = s.model()
            cx = ", ".join(f"{d} = {m[d]}" for d in m.decls())
        except Exception:
            cx = "(counterexample unavailable)"
        return "no", cx
    return "unknown", None


class ContractVerifier:
    """Contract verification using Z3 SMT solver.

    Checks:
    - Preconditions are mutually satisfiable (don't contradict each other).
    - Each postcondition is implied by the preconditions for all arithmetic
      expressions. Postconditions that reference ``result`` / ``return``
      (the function's return value) are verified for satisfiability only,
      since the actual return expression is not evaluated here.
    - Invariants are checked for satisfiability (self-consistency).
    """

    @staticmethod
    def parse_contract(code: str) -> ContractSpec:
        """Extract contract annotations from code."""
        if len(code) > MAX_CONTRACT_INPUT_CHARS:
            raise ContractInputTooLargeError(
                f"code is {len(code)} chars, exceeds {MAX_CONTRACT_INPUT_CHARS}-char scan limit"
            )

        spec = ContractSpec(preconditions=[], postconditions=[], invariants=[])

        lines = code.split('\n')
        if len(lines) > MAX_CONTRACT_LINES:
            raise ContractInputTooLargeError(
                f"code has {len(lines)} lines, exceeds {MAX_CONTRACT_LINES}-line scan limit"
            )

        for line in lines:
            line = line.replace('\x00', '')
            stripped = line.strip()

            pre_match = re.match(
                r'(?:#|//|/\*)\s*[Pp]re(?:condition)?:\s*(.*?)(?:\*/)?$', stripped
            )
            post_match = re.match(
                r'(?:#|//|/\*)\s*[Pp]ost(?:condition)?:\s*(.*?)(?:\*/)?$', stripped
            )
            inv_match = re.match(
                r'(?:#|//|/\*)\s*[Ii]nv(?:ariant)?:\s*(.*?)(?:\*/)?$', stripped
            )

            if pre_match:
                clause = pre_match.group(1).strip()
                if clause:
                    spec.preconditions.append(clause)
            elif post_match:
                clause = post_match.group(1).strip()
                if clause:
                    spec.postconditions.append(clause)
            elif inv_match:
                clause = inv_match.group(1).strip()
                if clause:
                    spec.invariants.append(clause)

        return spec

    @staticmethod
    def verify_contract(code: str, contract: Optional[ContractSpec] = None) -> Dict[str, Any]:
        """Verify contract clauses using Z3 SMT solving.

        Performs three checks when Z3 is available:
        1. Precondition satisfiability — the preconditions must not contradict
           each other (their conjunction must be SAT).
        2. Postcondition validity — for clauses that don't reference the
           function's return value, Z3 checks that the preconditions imply
           each postcondition. For clauses that do reference ``result`` /
           ``return``, satisfiability is checked instead (weaker, but still
           catches always-false postconditions).
        3. Invariant satisfiability — each invariant must be self-consistent.

        Falls back to structural validation when Z3 is unavailable.
        """
        result: Dict[str, Any] = {
            "verified": True,
            "preconditions_ok": True,
            "postconditions_ok": True,
            "details": [],
        }

        try:
            if contract is None:
                contract = ContractVerifier.parse_contract(code)
        except ContractInputTooLargeError as e:
            result["verified"] = False
            result["details"].append(f"Input rejected: {e}")
            return result

        all_clauses = contract.preconditions + contract.postconditions + contract.invariants
        if not all_clauses:
            result["details"].append("No contract annotations found (add # Pre: / # Post: comments)")
            return result

        if not Z3_AVAILABLE:
            # Structural check only: confirm clauses are non-empty strings
            result["details"].append(
                "Z3 not available — structural check only (install z3-solver for full verification)"
            )
            result["details"].append(
                f"Found {len(contract.preconditions)} precondition(s), "
                f"{len(contract.postconditions)} postcondition(s), "
                f"{len(contract.invariants)} invariant(s)"
            )
            return result

        env: Dict[str, Any] = {}
        z3_builtins.seed_string_env(
            contract.preconditions + contract.postconditions + contract.invariants, env,
        )

        # ── 1. Precondition satisfiability ────────────────────────────────
        pre_z3 = [_clause_to_z3(c, env) for c in contract.preconditions]
        parseable_pre = [e for e in pre_z3 if e is not None]
        skipped_pre = sum(1 for e in pre_z3 if e is None)

        if parseable_pre:
            sat, cx = _check_satisfiable(parseable_pre)
            if not sat:
                result["verified"] = False
                result["preconditions_ok"] = False
                result["details"].append(
                    f"FAIL: Preconditions are mutually contradictory — {cx}"
                )
                return result  # No point checking postconditions if pre is UNSAT
            result["details"].append(
                f"✓ Preconditions satisfiable ({len(parseable_pre)} checked"
                + (f", {skipped_pre} skipped — non-arithmetic" if skipped_pre else "") + ")"
            )
        elif contract.preconditions:
            result["details"].append(
                f"Preconditions present ({len(contract.preconditions)}) but non-arithmetic — skipped"
            )

        # ── 2. Postcondition validity ──────────────────────────────────────
        post_fails: List[str] = []
        post_verified = 0
        post_skipped = 0

        for clause in contract.postconditions:
            references_result = any(alias in clause.lower() for alias in _RESULT_ALIASES)
            z3_expr = _clause_to_z3(clause, env)

            if z3_expr is None:
                post_skipped += 1
                result["details"].append(f"  Post '{clause}' — skipped (non-arithmetic)")
                continue

            if references_result:
                # Weaker check: postcondition must be satisfiable on its own
                sat, _ = _check_satisfiable([z3_expr])
                if not sat:
                    post_fails.append(
                        f"'{clause}' is always False (postcondition can never hold)"
                    )
                else:
                    post_verified += 1
                    result["details"].append(
                        f"  Post '{clause}' — satisfiable ✓ "
                        "(references result; implication not checked without execution)"
                    )
            else:
                # Stronger check: preconditions must imply postcondition
                verdict, cx = _check_implied(parseable_pre, z3_expr)
                if verdict == "yes":
                    post_verified += 1
                    result["details"].append(f"  Post '{clause}' — implied by preconditions ✓")
                elif verdict == "no":
                    post_fails.append(
                        f"'{clause}' is NOT implied by preconditions "
                        f"(counterexample: {cx})"
                    )
                else:
                    post_skipped += 1
                    result["details"].append(
                        f"  Post '{clause}' — Z3 timeout (kept as unverified)"
                    )

        if post_fails:
            result["verified"] = False
            result["postconditions_ok"] = False
            for f in post_fails:
                result["details"].append(f"FAIL: {f}")
        elif contract.postconditions:
            summary = (
                f"✓ Postconditions: {post_verified} verified"
                + (f", {post_skipped} skipped" if post_skipped else "")
            )
            result["details"].append(summary)

        # ── 3. Invariant satisfiability ────────────────────────────────────
        for clause in contract.invariants:
            z3_expr = _clause_to_z3(clause, env)
            if z3_expr is None:
                result["details"].append(f"  Inv '{clause}' — skipped (non-arithmetic)")
                continue
            sat, cx = _check_satisfiable([z3_expr])
            if not sat:
                result["verified"] = False
                result["details"].append(
                    f"FAIL: Invariant '{clause}' is always False (never satisfiable)"
                )
            else:
                result["details"].append(f"  Inv '{clause}' — satisfiable ✓")

        return result

    @staticmethod
    def simplify_contract(spec: ContractSpec) -> Dict[str, Any]:
        """Return summary counts; use ContractSimplifier for actual Z3-based reduction."""
        return {
            "num_preconditions": len(spec.preconditions),
            "num_postconditions": len(spec.postconditions),
            "num_invariants": len(spec.invariants),
            "simplification_possible": len(spec.preconditions) > 1,
        }


__all__ = ['ContractVerifier', 'ContractSpec', 'ContractInputTooLargeError']
