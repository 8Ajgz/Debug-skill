"""PyProver Loop Invariant Verifier

Implements Hoare-logic loop invariant checking using Z3. For a while-loop with
an annotated invariant I and loop condition C:

  - INIT:         I holds at loop entry given the current symbolic environment
  - PRESERVATION: if I ∧ C holds at iteration k, then I holds after one body execution
  - POST-LOOP:    after the loop, the caller may assume I ∧ ¬C

Invariants are extracted from source comments in any of the following formats:
  Python:      # Invariant: expr   or   # Inv: expr
  C/C++/Java:  // Invariant: expr  or   /* Invariant: expr */
  Rust/Go:     // Invariant: expr

Z3 variables are created from the function's formal parameters (integers only in
this version) and from detected loop variables. Non-integer parameters are
skipped with a graceful note rather than failing hard.

This is the "bundled" loop verifier for debug-suite — it handles the most common
case (integer arithmetic invariants like `i >= 0`, `i <= n`, `total == i * (i+1) / 2`)
that covers real-world loop verification use. It does NOT perform full symbolic
execution of arbitrary loop bodies; see legacy_code/pyprover_v13_loop_verifier.py
for the design sketch of a more general version.
"""

import re
import ast
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

try:
    import z3
    from z3.z3util import get_vars
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False

from . import z3_builtins


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LoopInvariant:
    """A single loop invariant extracted from source."""
    expression: str
    line_number: Optional[int] = None
    loop_var: Optional[str] = None    # primary iteration variable (e.g. 'i')


@dataclass
class LoopVerificationResult:
    """Result of verifying a single loop invariant expression."""
    invariant: str
    init_holds: Optional[bool] = None       # None: not checked (entry value unknown)
    preservation_holds: Optional[bool] = None   # None: not checked (no iteration variable)
    post_loop_sound: bool = False     # I ∧ ¬C is consistent (non-vacuous)
    error: Optional[str] = None
    counterexample: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None

    @property
    def fully_verified(self) -> bool:
        return self.init_holds is True and self.preservation_holds is True and not self.skipped


@dataclass
class LoopVerificationReport:
    """Aggregate report for all invariants found in a function."""
    invariants_found: int = 0
    results: List[LoopVerificationResult] = field(default_factory=list)
    z3_available: bool = False
    parse_error: Optional[str] = None

    @property
    def all_verified(self) -> bool:
        return (
            self.invariants_found > 0
            and all(r.fully_verified for r in self.results)
        )

    def summary(self) -> str:
        if self.parse_error:
            return f"Parse error: {self.parse_error}"
        if not self.z3_available:
            return "Z3 not available — install z3-solver to enable loop verification"
        if self.invariants_found == 0:
            return (
                "No loop invariants found. "
                "Annotate while-loops with  # Invariant: <expr>  to enable verification."
            )
        lines = [f"Loop Invariant Verification ({self.invariants_found} invariant(s)):"]
        for r in self.results:
            if r.skipped:
                lines.append(f"  [SKIPPED] {r.invariant} — {r.skip_reason}")
            elif r.fully_verified:
                lines.append(f"  [VERIFIED] {r.invariant}")
                lines.append(f"             INIT=✅  PRESERVATION=✅")
            else:
                lines.append(f"  [FAILED]   {r.invariant}")
                lines.append(
                    f"             INIT={'✅' if r.init_holds else '❌'}  "
                    f"PRESERVATION={'✅' if r.preservation_holds else '❌'}"
                )
                if r.error:
                    lines.append(f"             Error: {r.error}")
                if r.counterexample:
                    lines.append(f"             Counterexample: {r.counterexample}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Invariant extraction
# ---------------------------------------------------------------------------

# Patterns: match  # Invariant: expr   //Invariant: expr   /* Inv: expr */
from .contract_verifier import _DECORATOR_CONTRACT_RE, _STRING_PIECE_RE

_INVARIANT_RE = re.compile(
    r"(?:#|//|/\*)\s*[Ii]nv(?:ariant)?:\s*(.*?)(?:\*/)?$"
)


def extract_loop_invariants(source_code: str) -> List[LoopInvariant]:
    """Extract ``# Invariant: <expr>`` and ``@loop_invariant("<expr>")`` from source_code."""
    invariants: List[LoopInvariant] = []
    for lineno, line in enumerate(source_code.splitlines(), start=1):
        m = _INVARIANT_RE.match(line.strip())
        if m:
            expr = m.group(1).strip()
            if expr:
                invariants.append(LoopInvariant(expression=expr, line_number=lineno))
    for m in _DECORATOR_CONTRACT_RE.finditer(source_code):
        if m.group(1) != "loop_invariant":
            continue
        text = "".join(a if a or not b else b for a, b in _STRING_PIECE_RE.findall(m.group(2))).strip()
        if text:
            line_number = source_code.count("\n", 0, m.start()) + 1
            invariants.append(LoopInvariant(expression=text, line_number=line_number))
    invariants.sort(key=lambda inv: inv.line_number or 0)
    return invariants


# ---------------------------------------------------------------------------
# Simple Z3 expression parser for arithmetic invariants
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
    ast.And:    lambda a, b: z3.And(a, b),
    ast.Or:     lambda a, b: z3.Or(a, b),
    ast.Not:    lambda a: z3.Not(a),
}


def _expr_to_z3(node: ast.expr, env: Dict[str, Any]) -> Any:
    """Recursively convert an ast.expr into a Z3 expression."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return z3.StringVal(node.value)
        return node.value
    if isinstance(node, ast.Name):
        name = node.id
        if name in env:
            return env[name]
        # Create a fresh Int variable on demand
        v = z3.Int(name)
        env[name] = v
        return v
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
                raise NotImplementedError(f"Unsupported Compare op: {type(op).__name__}")
            part = cmp(left, right)
            result = part if result is None else z3.And(result, part)
            left = right
        return result
    if isinstance(node, ast.Call):
        if (isinstance(node.func, ast.Name) and node.func.id in ("all", "any")
                and len(node.args) == 1 and isinstance(node.args[0], ast.GeneratorExp)):
            return _quantifier_to_z3(node.func.id, node.args[0], env)
        result = z3_builtins.try_call_to_z3(node, env, _expr_to_z3)
        if result is not None:
            return result
        raise NotImplementedError(f"Unsupported call: {ast.dump(node.func)}")
    raise NotImplementedError(f"Unsupported node type: {type(node).__name__}")


def _quantifier_to_z3(kind: str, gen: ast.GeneratorExp, env: Dict[str, Any]) -> Any:
    """Translate ``all(c for k in range(lo, hi))`` to ForAll, ``any(...)`` to Exists.

    The bound variable is local to the quantifier. Bounds may use loop variables,
    so a quantified invariant such as ``all(k < i for k in range(0, i))`` is checked
    in INIT and PRESERVATION like any other invariant.
    """
    if len(gen.generators) != 1 or not isinstance(gen.generators[0].target, ast.Name):
        raise NotImplementedError("quantifier needs exactly one loop variable")
    comp = gen.generators[0]
    if comp.ifs or comp.is_async:
        raise NotImplementedError("quantifier filters are not supported")
    rng = comp.iter
    if not (isinstance(rng, ast.Call) and isinstance(rng.func, ast.Name) and rng.func.id == "range"):
        raise NotImplementedError("quantifier domain must be range(...)")
    if len(rng.args) == 1:
        lo_node, hi_node = ast.Constant(value=0), rng.args[0]
    elif len(rng.args) == 2:
        lo_node, hi_node = rng.args
    else:
        raise NotImplementedError("range() takes one or two arguments in a quantifier")
    lo = _expr_to_z3(lo_node, env)
    hi = _expr_to_z3(hi_node, env)
    var = z3.Int(comp.target.id)
    inner = dict(env)
    inner[comp.target.id] = var
    body = _expr_to_z3(gen.elt, inner)
    in_range = z3.And(lo <= var, var < hi)
    if kind == "all":
        return z3.ForAll([var], z3.Implies(in_range, body))
    return z3.Exists([var], z3.And(in_range, body))


def _parse_invariant_expr(expr_str: str, env: Dict[str, Any]) -> Any:
    """Parse an invariant expression string into a Z3 expression."""
    tree = ast.parse(expr_str, mode="eval")
    return _expr_to_z3(tree.body, env)


# ---------------------------------------------------------------------------
# Proof obligation construction
# ---------------------------------------------------------------------------

def _check_sat(solver: "z3.Solver", timeout_ms: int = 5000) -> str:
    """Return 'sat', 'unsat', or 'unknown'."""
    solver.set("timeout", timeout_ms)
    r = solver.check()
    return str(r)


def verify_loop_invariant(
    invariant: LoopInvariant,
    param_names: List[str],
    timeout_ms: int = 5000,
    entry: Optional[Dict[str, int]] = None,
) -> LoopVerificationResult:
    """Verify INIT and PRESERVATION for a single loop invariant.

    param_names: names of the function's integer-typed parameters, used to
                 seed the symbolic environment before checking INIT.
    entry:       known integer values at loop entry. INIT is checked only when
                 every variable in the invariant has a known value.

    The verification strategy:
      INIT: assert ¬I in a fresh solver with standard integer bounds;
            if UNSAT, I is valid at entry (for all input values it holds).
            We use the weaker check: I is satisfiable (consistent) at entry.
      PRESERVATION: assert I ∧ loop-continues (iter var increments by 1),
                    then assert ¬I'; if UNSAT, I is inductive.
    """
    result = LoopVerificationResult(invariant=invariant.expression)

    if not Z3_AVAILABLE:
        result.skipped = True
        result.skip_reason = "z3-solver not installed"
        return result

    # Build initial symbolic environment from parameter names
    env: Dict[str, Any] = {name: z3.Int(name) for name in param_names}
    z3_builtins.seed_string_env([invariant.expression], env)

    # ------------------------------------------------------------------
    # INIT: the invariant must hold at loop entry. That needs the entry values,
    # which verify_source reads from the assignments before the loop. Without
    # them, INIT is not checked (init_holds stays None). Satisfiability is not
    # enough: "i >= 0" is satisfiable but false when i starts at -1.
    # ------------------------------------------------------------------
    try:
        inv_expr = _parse_invariant_expr(invariant.expression, env)
    except NotImplementedError as e:
        result.skipped = True
        result.skip_reason = f"Unsupported expression: {e}"
        return result
    except Exception as e:
        result.skipped = True
        result.skip_reason = f"Parse/Z3 error: {e}"
        return result

    free_names = {str(v) for v in get_vars(inv_expr)}
    known = dict(entry or {})
    if not free_names <= set(known):
        missing = sorted(free_names - set(known))
        result.error = (f"INIT not checked: entry value unknown for {', '.join(missing)}"
                        if missing else "INIT not checked: no entry values")
    else:
        s_init = z3.Solver()
        s_init.set("timeout", timeout_ms)
        for name, value in known.items():
            if name in env:
                s_init.add(env[name] == value)
        s_init.add(z3.Not(inv_expr))
        res = _check_sat(s_init, timeout_ms)
        if res == "unsat":
            result.init_holds = True
        elif res == "sat":
            result.init_holds = False
            result.error = "Invariant does not hold at loop entry"
            result.post_loop_sound = False
            return result
        else:
            result.error = "Z3 returned unknown on INIT check"

    # ------------------------------------------------------------------
    # PRESERVATION: assume I holds at iteration k; increment iteration
    # variable by 1; check that I still holds.
    #
    # We look for a variable named 'i', 'j', 'k', 'idx', or the loop_var
    # hint. If found, model one iteration step (var += 1) and check I'.
    # ------------------------------------------------------------------
    try:
        all_vars = {**env}
        inv_expr_fresh = _parse_invariant_expr(invariant.expression, all_vars)
        new_vars = {k: v for k, v in all_vars.items() if k not in env}

        # Find the iteration variable (primary candidate)
        iter_var = invariant.loop_var
        if iter_var is None:
            for candidate in ("i", "j", "k", "idx", "n", "count"):
                if candidate in all_vars:
                    iter_var = candidate
                    break

        if iter_var and iter_var in all_vars:
            # Create post-iteration environment: iter_var' = iter_var + 1
            post_env = dict(all_vars)
            iter_sym = all_vars[iter_var]
            iter_sym_post = z3.Int(f"{iter_var}__post")
            post_env[iter_var] = iter_sym_post

            inv_pre = _parse_invariant_expr(invariant.expression, dict(all_vars))
            inv_post = _parse_invariant_expr(invariant.expression, post_env)

            s_pres = z3.Solver()
            # Assume bounds and I at start of iteration
            for v in all_vars.values():
                if isinstance(v, z3.ArithRef):
                    s_pres.add(v >= 0, v <= 100_000)
            s_pres.add(inv_pre)
            # Model one step: post = pre + 1
            s_pres.add(iter_sym_post == iter_sym + 1)
            s_pres.add(iter_sym_post <= 100_000)
            # Check ¬I' — if UNSAT, I is preserved
            s_pres.add(z3.Not(inv_post))
            res = _check_sat(s_pres, timeout_ms)
            if res == "unsat":
                result.preservation_holds = True
            elif res == "sat":
                model = s_pres.model()
                result.preservation_holds = False
                result.counterexample = str(model)
            else:
                # unknown — be conservative, mark as skipped
                result.preservation_holds = False
                result.error = "Z3 returned unknown on PRESERVATION check"
        else:
            # No iteration variable found: preservation is not checked (None), not assumed
            result.preservation_holds = None
            result.error = (
                "No iteration variable found (expected 'i', 'j', 'k', etc.); "
                "PRESERVATION not checked."
            )
    except NotImplementedError as e:
        result.preservation_holds = False
        result.error = f"Unsupported expression in PRESERVATION: {e}"
    except Exception as e:
        result.preservation_holds = False
        result.error = f"PRESERVATION check error: {e}"

    result.post_loop_sound = result.init_holds is True
    return result


# ---------------------------------------------------------------------------
# High-level LoopVerifier
# ---------------------------------------------------------------------------

def _entry_values(source_code: str, before_line: int) -> Dict[str, int]:
    """Integer values assigned at top level before ``before_line``, as known at loop entry.

    A name counts only if its last top-level assignment before the loop is an integer
    constant. Any other assignment, or a for-loop target, removes the name.
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return {}
    values: Dict[str, int] = {}
    for stmt in tree.body:
        if stmt.lineno >= before_line:
            break
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            value = stmt.value
            sign = 1
            if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.USub):
                sign, value = -1, value.operand
            if isinstance(value, ast.Constant) and isinstance(value.value, int) and not isinstance(value.value, bool):
                values[stmt.targets[0].id] = sign * value.value
                continue
        targets = []
        if isinstance(stmt, ast.Assign):
            targets = [t for t in stmt.targets if isinstance(t, ast.Name)]
        elif isinstance(stmt, (ast.AugAssign, ast.AnnAssign)) and isinstance(stmt.target, ast.Name):
            targets = [stmt.target]
        elif isinstance(stmt, ast.For) and isinstance(stmt.target, ast.Name):
            targets = [stmt.target]
        for t in targets:
            values.pop(t.id, None)
    return values


class LoopVerifier:
    """High-level loop invariant verifier.

    Usage::

        verifier = LoopVerifier()
        report = verifier.verify_source(source_code, param_names=["n"])
        print(report.summary())
    """

    def __init__(self, timeout_ms: int = 5000):
        self.timeout_ms = timeout_ms

    def verify_source(
        self,
        source_code: str,
        param_names: Optional[List[str]] = None,
    ) -> LoopVerificationReport:
        """Extract and verify all loop invariants found in source_code."""
        report = LoopVerificationReport(z3_available=Z3_AVAILABLE)

        if not Z3_AVAILABLE:
            return report

        try:
            invariants = extract_loop_invariants(source_code)
        except Exception as e:
            report.parse_error = str(e)
            return report

        report.invariants_found = len(invariants)
        pnames = param_names or []

        for inv in invariants:
            entry = _entry_values(source_code, inv.line_number or 0)
            r = verify_loop_invariant(inv, pnames, self.timeout_ms, entry=entry)
            report.results.append(r)

        return report
