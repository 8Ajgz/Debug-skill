"""PyProver Equivalence Verifier

Proves whether two pieces of code compute the same result for all inputs
(within this module's supported subset), and — for the same subset —
derives an algebraically simplified equivalent via Z3's own term rewriter.

SCOPE, STATED UP FRONT: this is NOT general program synthesis. "Find the
objectively simplest equivalent program for arbitrary code" is undecidable
in general for Turing-complete languages (two programs' equivalence is a
Rice's-theorem-class problem — there is no algorithm that decides this for
every pair of programs). This module does two much narrower, but real and
sound, things instead:

1. VERIFY: given two functions (or two standalone expressions), symbolically
   execute both over the same symbolic inputs and prove their outputs are
   equal for every input — or find a concrete counterexample where they
   differ. This is the useful, general-purpose piece: you (or a rewrite
   pattern below) propose a simplification, this proves whether it's
   actually correct before anyone trusts it.

2. SIMPLIFY: for the same supported subset, build a symbolic Z3 expression
   for the function's return value and hand it to Z3's own `simplify()`
   tactic — a real, sound term-rewriting engine (constant folding, boolean
   algebra, arithmetic normalization), not a guess or an LLM paraphrase.
   The result is a genuine algebraic simplification of what the code
   computes, not a suggestion that still needs separate verification.

SUPPORTED SUBSET (straight-line + branching, no loops in the general path):
  - Assignment to a simple name: `x = <expr>`, `x += <expr>` etc.
  - `if`/`elif`/`else` with `return` in (some) branches, including
    fall-through to a trailing return
  - Expressions: the same integer/boolean arithmetic `contract_verifier.py`
    already supports (+, -, *, //, /, %, comparisons, and/or/not) via its
    `_expr_to_z3` — reused here, not reimplemented
  - A single BOUNDED loop path: `for i in range(N)` where N is a literal or
    a symbolic parameter capped at `max_unroll` — unrolled, not reasoned
    about via invariants. This is the same bounded-model-checking principle
    already used elsewhere in this suite (CBMC/KLEE, `symbolic_executor.py`)
    for C/C++: sound *up to the unroll bound*, not a proof for all N unless
    N is fixed and within the bound.

NOT SUPPORTED, HONESTLY, NOT SILENTLY: function calls other than the
built-in operators above, list/dict/string operations, recursion, unbounded
or nested loops, mutation of aliased objects, generators, exceptions as
control flow, multiple return values, or a bare boolean-typed variable used
directly with and/or/not (e.g. `not flag`) — the reused `_expr_to_z3`
always seeds an unbound name as a Z3 `Int`, so a bare boolean name conflicts
with `Not()`; use an Int-typed comparison instead (e.g. `flag > 0`), which
is unambiguously `Bool`-sorted. Hitting any of these raises
`UnsupportedConstructError` with the specific construct named — this module
never silently produces a false "equivalent" or a wrong "simplified" result
for code it can't actually reason about. Compare
`pyprover/loop_verifier.py`'s own disclosed scope limits (INIT/PRESERVATION
only, no TERMINATION) — same honesty discipline, different feature.
"""

import ast
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False

from .contract_verifier import _expr_to_z3, _OP_MAP

_Z3_TIMEOUT_MS = 5000
DEFAULT_MAX_UNROLL = 64


class UnsupportedConstructError(ValueError):
    """Raised when code uses a construct outside this module's supported
    subset. Callers must treat this as 'cannot determine', never as
    'equivalent' or 'not equivalent' — see module docstring."""


def _expr_to_z3_safe(node: ast.expr, env: Dict[str, Any]) -> Any:
    """Wraps the reused contract_verifier._expr_to_z3 to convert its raw
    NotImplementedError (its convention for "unsupported node type", e.g.
    function calls, attribute access) into this module's
    UnsupportedConstructError, so every caller in this file can catch one
    consistent exception type instead of two."""
    for sub in ast.walk(node):
        # Z3's div/mod are Euclidean, so they differ from Python's // and %
        # whenever the divisor is negative or symbolic (Python: 7 % -2 == -1,
        # Z3 mod(7, -2) == 1). Only a positive literal divisor is safe.
        if (isinstance(sub, ast.BinOp) and isinstance(sub.op, (ast.FloorDiv, ast.Mod))
                and not (isinstance(sub.right, ast.Constant)
                         and type(sub.right.value) is int and sub.right.value > 0)):
            raise UnsupportedConstructError(
                "'//' and '%' are only supported with a positive integer literal "
                "divisor (Z3 uses Euclidean division, which differs from Python "
                "for negative or symbolic divisors)"
            )
    try:
        return _expr_to_z3(node, env)
    except NotImplementedError as e:
        raise UnsupportedConstructError(str(e))


@dataclass
class EquivalenceResult:
    """Result of verify_function_equivalence() / verify_expression_equivalence().

    `equivalent` is only meaningful when `status == "decided"`. A `status`
    of "unsupported" or "unknown" means no equivalence claim was made
    either way — always check `status` before trusting `equivalent`.
    """
    status: str  # "decided" | "unsupported" | "unknown" (Z3 timeout)
    equivalent: Optional[bool] = None
    counterexample: Optional[str] = None
    reason: Optional[str] = None  # populated for "unsupported"/"unknown"
    proof_a: Optional[str] = None  # str() of the symbolic expr built for A
    proof_b: Optional[str] = None  # str() of the symbolic expr built for B

    def summary(self) -> str:
        if self.status == "unsupported":
            return f"Cannot determine — unsupported construct: {self.reason}"
        if self.status == "unknown":
            return f"Cannot determine — Z3 timed out: {self.reason}"
        if self.equivalent:
            return "PROVEN EQUIVALENT for all inputs in the supported domain."
        return f"NOT EQUIVALENT — counterexample: {self.counterexample}"


@dataclass
class SimplificationResult:
    """Result of simplify_function()."""
    status: str  # "simplified" | "already_simplest" | "unsupported"
    original_expr: Optional[str] = None
    simplified_expr: Optional[str] = None  # Z3 string form
    reason: Optional[str] = None
    simplified_python: Optional[str] = None  # runnable Python expression over the same parameter names

    def summary(self) -> str:
        if self.status == "unsupported":
            return f"Cannot simplify — unsupported construct: {self.reason}"
        if self.status == "already_simplest":
            return f"No algebraic simplification found: {self.original_expr}"
        if self.simplified_python is not None:
            return f"{self.original_expr}  =>  {self.simplified_python}"
        return f"{self.original_expr}  =>  {self.simplified_expr}"


# ---------------------------------------------------------------------------
# Statement-level symbolic execution (the actual new capability — everything
# above _expr_to_z3 is leaf-expression translation reused from
# contract_verifier.py; this is the statement/control-flow layer on top)
# ---------------------------------------------------------------------------

def _find_function(code: str, func_name: str) -> ast.FunctionDef:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise UnsupportedConstructError(f"syntax error: {e}")
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return node
    raise UnsupportedConstructError(f"function '{func_name}' not found")


# A statement list, once executed, either definitely returns a value on
# every path within it ("return", z3_expr) or falls off the end having only
# updated the environment ("fallthrough", env). Every `if` must combine two
# flows of the SAME kind (both return, or both fall through) — a branch
# where one side returns and the other doesn't is rejected explicitly
# rather than guessed at, since silently picking a behavior there would be
# exactly the kind of unsound shortcut this module exists to avoid.

def _exec_stmts(
    stmts: List[ast.stmt],
    env: Dict[str, Any],
    max_unroll: int,
) -> Tuple[str, Any]:
    for idx, stmt in enumerate(stmts):
        if isinstance(stmt, ast.Return):
            if stmt.value is None:
                raise UnsupportedConstructError("bare 'return' (no value)")
            return ("return", _expr_to_z3_safe(stmt.value, env))

        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise UnsupportedConstructError(
                    "assignment target must be a single simple name"
                )
            env[stmt.targets[0].id] = _expr_to_z3_safe(stmt.value, env)
            continue

        if isinstance(stmt, ast.AugAssign):
            if not isinstance(stmt.target, ast.Name):
                raise UnsupportedConstructError(
                    "augmented-assignment target must be a simple name"
                )
            name = stmt.target.id
            if name not in env:
                env[name] = z3.Int(name)
            op = _OP_MAP.get(type(stmt.op))
            if op is None:
                raise UnsupportedConstructError(
                    f"unsupported augmented-assignment operator: {type(stmt.op).__name__}"
                )
            env[name] = op(env[name], _expr_to_z3_safe(stmt.value, env))
            continue

        if isinstance(stmt, ast.If):
            cond = _expr_to_z3_safe(stmt.test, env)

            then_env = dict(env)
            then_flow = _exec_stmts(stmt.body, then_env, max_unroll)

            else_env = dict(env)
            if stmt.orelse:
                else_flow = _exec_stmts(stmt.orelse, else_env, max_unroll)
            else:
                else_flow = ("fallthrough", else_env)

            if then_flow[0] == "return" and else_flow[0] == "return":
                return ("return", z3.If(cond, then_flow[1], else_flow[1]))

            if then_flow[0] == "fallthrough" and else_flow[0] == "fallthrough":
                merged: Dict[str, Any] = {}
                for name in set(then_env) | set(else_env):
                    tv = then_env.get(name, env.get(name))
                    ev = else_env.get(name, env.get(name))
                    if tv is None or ev is None:
                        continue
                    merged[name] = tv if (tv is ev) else z3.If(cond, tv, ev)
                env.update(merged)
                return _exec_stmts(list(stmts[idx + 1:]), env, max_unroll)

            # Exactly one branch returns and the other falls through: this
            # is the ordinary "early return" pattern (`if cond: return X` /
            # then more code, or the mirror image). The branch that falls
            # through continues into the REMAINING statements (using its
            # own env), and that remainder must itself resolve to a
            # definite return for the combination to be well-defined -
            # otherwise the function genuinely doesn't return on every
            # path, which is correctly rejected rather than guessed at.
            if then_flow[0] == "return" and else_flow[0] == "fallthrough":
                remainder = _exec_stmts(list(stmts[idx + 1:]), else_env, max_unroll)
                if remainder[0] != "return":
                    raise UnsupportedConstructError(
                        "function does not return a value on every path"
                    )
                return ("return", z3.If(cond, then_flow[1], remainder[1]))

            if then_flow[0] == "fallthrough" and else_flow[0] == "return":
                remainder = _exec_stmts(list(stmts[idx + 1:]), then_env, max_unroll)
                if remainder[0] != "return":
                    raise UnsupportedConstructError(
                        "function does not return a value on every path"
                    )
                return ("return", z3.If(cond, remainder[1], else_flow[1]))

            raise UnsupportedConstructError("unreachable if/else flow combination")

        if isinstance(stmt, ast.For):
            if not (isinstance(stmt.iter, ast.Call)
                    and isinstance(stmt.iter.func, ast.Name)
                    and stmt.iter.func.id == "range"
                    and isinstance(stmt.target, ast.Name)):
                raise UnsupportedConstructError(
                    "only 'for x in range(...)' loops are supported"
                )
            if any(isinstance(n, ast.Return) for n in ast.walk(ast.Module(body=stmt.body, type_ignores=[]))):
                raise UnsupportedConstructError(
                    "'return' inside a loop body is not supported"
                )
            if len(stmt.iter.args) == 1:
                start, bound_node = 0, stmt.iter.args[0]
            elif len(stmt.iter.args) == 2:
                start_node, bound_node = stmt.iter.args
                if not (isinstance(start_node, ast.Constant) and isinstance(start_node.value, int)):
                    raise UnsupportedConstructError("range() start must be a literal integer")
                start = start_node.value
            else:
                raise UnsupportedConstructError("range() with a step argument is not supported")

            if not isinstance(bound_node, ast.Constant) or not isinstance(bound_node.value, int):
                raise UnsupportedConstructError(
                    "loop bound must be a literal integer for unrolling "
                    "(symbolic bounds are not supported — this is a bounded "
                    "unroll, not an invariant-based proof)"
                )
            bound = bound_node.value
            if (bound - start) > max_unroll:
                raise UnsupportedConstructError(
                    f"loop has {bound - start} iterations, exceeds "
                    f"max_unroll={max_unroll} (raise max_unroll explicitly "
                    "if you accept the cost — this is bounded verification, "
                    "same principle as this suite's CBMC/KLEE integration)"
                )

            loop_var = stmt.target.id
            for i in range(start, bound):
                env[loop_var] = i
                body_flow = _exec_stmts(list(stmt.body), env, max_unroll)
                assert body_flow[0] == "fallthrough"  # guaranteed by the Return check above
                env.update(body_flow[1] if isinstance(body_flow[1], dict) else env)
            continue

        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue  # bare docstring/comment-as-string

        raise UnsupportedConstructError(f"unsupported statement: {type(stmt).__name__}")

    return ("fallthrough", env)


def _function_to_symbolic(
    func_node: ast.FunctionDef,
    shared_env: Dict[str, Any],
    max_unroll: int,
) -> Any:
    """Symbolically execute a function, returning the Z3 expression for its
    return value. `shared_env` seeds parameter names with shared Z3
    variables so two functions being compared reference the SAME symbolic
    inputs (required for a meaningful equivalence check)."""
    env = dict(shared_env)
    for arg in func_node.args.args:
        if arg.arg not in env:
            env[arg.arg] = z3.Int(arg.arg)
    flow = _exec_stmts(list(func_node.body), env, max_unroll)
    if flow[0] != "return":
        raise UnsupportedConstructError(
            "function does not return a value on every path"
        )
    return flow[1]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_expression_equivalence(expr_a: str, expr_b: str) -> EquivalenceResult:
    """Prove whether two standalone expressions (e.g. "x + x + x" and
    "3 * x") compute the same value for all inputs. Shares free variables
    by name between the two expressions."""
    if not Z3_AVAILABLE:
        return EquivalenceResult(status="unsupported", reason="z3-solver not installed")

    env: Dict[str, Any] = {}
    try:
        tree_a = ast.parse(expr_a, mode="eval")
        tree_b = ast.parse(expr_b, mode="eval")
        za = _expr_to_z3_safe(tree_a.body, env)
        zb = _expr_to_z3_safe(tree_b.body, env)
    except SyntaxError as e:
        return EquivalenceResult(status="unsupported", reason=f"syntax error: {e}")
    except UnsupportedConstructError as e:
        return EquivalenceResult(status="unsupported", reason=str(e))
    except z3.Z3Exception as e:
        return EquivalenceResult(
            status="unsupported",
            reason=f"Z3 sort mismatch: {e} (note: every free variable is "
                   "treated as an Int by the underlying expression "
                   "translator — a bare boolean name like 'a' in 'a and b' "
                   "will conflict with 'not a'; use an Int-typed comparison "
                   "instead, e.g. 'a > 0', which is unambiguously Bool-sorted)",
        )

    return _prove_equal(za, zb)


def verify_function_equivalence(
    code_a: str,
    func_a: str,
    code_b: str,
    func_b: str,
    max_unroll: int = DEFAULT_MAX_UNROLL,
) -> EquivalenceResult:
    """Prove whether two functions compute the same return value for all
    inputs, within this module's supported subset (see module docstring).
    The two functions are matched positionally by parameter order, not by
    name — `func_a(x, y)` and `func_b(a, b)` are compared with `x`/`a` and
    `y`/`b` bound to the same symbolic variables.
    """
    if not Z3_AVAILABLE:
        return EquivalenceResult(status="unsupported", reason="z3-solver not installed")

    try:
        node_a = _find_function(code_a, func_a)
        node_b = _find_function(code_b, func_b)
    except UnsupportedConstructError as e:
        return EquivalenceResult(status="unsupported", reason=str(e))

    params_a = [a.arg for a in node_a.args.args]
    params_b = [a.arg for a in node_b.args.args]
    if len(params_a) != len(params_b):
        return EquivalenceResult(
            status="unsupported",
            reason=f"parameter count differs: {func_a} has {len(params_a)}, "
                   f"{func_b} has {len(params_b)}",
        )

    shared_vars = [z3.Int(f"_arg{i}") for i in range(len(params_a))]
    env_a = {name: var for name, var in zip(params_a, shared_vars)}
    env_b = {name: var for name, var in zip(params_b, shared_vars)}

    try:
        result_a = _function_to_symbolic(node_a, env_a, max_unroll)
        result_b = _function_to_symbolic(node_b, env_b, max_unroll)
    except UnsupportedConstructError as e:
        return EquivalenceResult(status="unsupported", reason=str(e))
    except z3.Z3Exception as e:
        return EquivalenceResult(
            status="unsupported",
            reason=f"Z3 sort mismatch: {e} (every parameter is treated as "
                   "an Int by the underlying expression translator; a "
                   "parameter used as a bare boolean, e.g. 'if not flag:', "
                   "will conflict — use an Int-typed comparison instead)",
        )

    result = _prove_equal(result_a, result_b)
    result.proof_a = str(result_a)
    result.proof_b = str(result_b)
    return result


_Z3_PY_BINARY = {
    "+": "+", "-": "-", "*": "*", "/": "/", "div": "//", "mod": "%",
    "<": "<", "<=": "<=", ">": ">", ">=": ">=", "=": "==", "distinct": "!=",
}


def _z3_to_python(expr: Any, names: Optional[frozenset] = None) -> str:
    """Render a Z3 expression as Python source over the same parameter names.

    `names` is the set of parameter names the output may refer to. A free
    symbol outside it (e.g. the stand-in Z3 uses for len(x)) cannot be
    rendered, so it raises instead of producing an unbound name.

    Raises UnsupportedConstructError for any Z3 node this does not handle, so
    the caller can fall back to the Z3 string form instead of emitting wrong code.
    """
    if z3.is_string_value(expr):
        return repr(expr.as_string())
    if z3.is_true(expr):
        return "True"
    if z3.is_false(expr):
        return "False"
    if z3.is_int_value(expr):
        v = expr.as_long()
        return f"({v})" if v < 0 else str(v)
    if z3.is_rational_value(expr):
        num, den = expr.numerator_as_long(), expr.denominator_as_long()
        return f"({num}/{den})"
    if z3.is_const(expr):
        symbol = expr.decl().name()
        if names is not None and symbol not in names:
            raise UnsupportedConstructError(f"symbol '{symbol}' is not a parameter")
        return symbol

    name = expr.decl().name()
    args = [_z3_to_python(expr.arg(i), names) for i in range(expr.num_args())]
    if name == "to_real" and len(args) == 1:
        return args[0]
    if name == "if" and len(args) == 3:
        return f"({args[1]} if {args[0]} else {args[2]})"
    if name == "not" and len(args) == 1:
        return f"(not {args[0]})"
    if name in ("and", "or") and args:
        return "(" + f" {name} ".join(args) + ")"
    if name == "-" and len(args) == 1:
        return f"(-{args[0]})"
    if name in ("+", "*") and len(args) >= 2:   # Z3 sums and products are n-ary
        return "(" + f" {name} ".join(args) + ")"
    if name in _Z3_PY_BINARY and len(args) == 2:
        return f"({args[0]} {_Z3_PY_BINARY[name]} {args[1]})"
    raise UnsupportedConstructError(f"no Python rendering for Z3 operator '{name}'")


def _z3_size(expr: Any, memo: Optional[Dict[int, int]] = None) -> int:
    """Number of nodes in the expression as a tree (a shared sub-term is counted
    at each place it appears). Memoised per sub-term, so DAG-shaped Z3 terms
    are measured in linear time."""
    if memo is None:
        memo = {}
    key = expr.get_id()
    if key not in memo:
        memo[key] = 1 + sum(_z3_size(expr.arg(i), memo) for i in range(expr.num_args()))
    return memo[key]


def simplify_function(
    code: str,
    func_name: str,
    max_unroll: int = DEFAULT_MAX_UNROLL,
) -> SimplificationResult:
    """Derive an algebraically simplified equivalent of a function's return
    value using Z3's own sound term-rewriting simplifier — a real
    simplification of what the code computes, not a suggestion.

    The output is a Z3 expression's string form, not runnable Python — it
    tells you *what the code algebraically reduces to* (e.g. a deeply
    nested if-chain reducing to a single comparison), which is the
    actually-hard part; turning that back into idiomatic Python is a
    mechanical follow-up, not a soundness question.
    """
    if not Z3_AVAILABLE:
        return SimplificationResult(status="unsupported", reason="z3-solver not installed")

    try:
        node = _find_function(code, func_name)
    except UnsupportedConstructError as e:
        return SimplificationResult(status="unsupported", reason=str(e))

    env: Dict[str, Any] = {}
    try:
        original = _function_to_symbolic(node, env, max_unroll)
    except UnsupportedConstructError as e:
        return SimplificationResult(status="unsupported", reason=str(e))
    except z3.Z3Exception as e:
        return SimplificationResult(
            status="unsupported",
            reason=f"Z3 sort mismatch: {e} (every parameter is treated as "
                   "an Int by the underlying expression translator; a "
                   "parameter used as a bare boolean will conflict — use "
                   "an Int-typed comparison instead)",
        )

    try:
        simplified = z3.simplify(original)
    except Exception as e:
        return SimplificationResult(status="unsupported", reason=f"Z3 simplify() failed: {e}")

    original_str = str(original)
    simplified_str = str(simplified)

    # Z3 also reorders terms, e.g. "100 + a*50" becomes "100 + 50*a", which is
    # not a simplification. Only a result with fewer nodes is reported.
    if original_str == simplified_str or _z3_size(simplified) >= _z3_size(original):
        return SimplificationResult(status="already_simplest", original_expr=original_str)

    # Safety net: the rewrite is only reported if the solver confirms it is
    # equal to the original for every input. Anything else is not a simplification.
    proof = _prove_equal(original, simplified)
    if proof.status != "decided" or not proof.equivalent:
        return SimplificationResult(
            status="unsupported",
            original_expr=original_str,
            reason=f"simplified form could not be confirmed equal to the original ({proof.summary()})",
        )

    try:
        simplified_python = _z3_to_python(simplified, frozenset(a.arg for a in node.args.args))
    except UnsupportedConstructError:
        simplified_python = None

    return SimplificationResult(
        status="simplified",
        original_expr=original_str,
        simplified_expr=simplified_str,
        simplified_python=simplified_python,
    )


# ---------------------------------------------------------------------------
# Small set of known-safe rewrite pattern proposals (NOT open-ended search —
# a short, honest, hand-written list; every candidate is verified before
# being returned, never presented on pattern-match confidence alone)
# ---------------------------------------------------------------------------

def propose_redundant_branch_removal(code: str, func_name: str) -> Optional[Tuple[str, EquivalenceResult]]:
    """If a function is 'if cond: return X else: return X' with the same
    expression in both branches, propose collapsing to 'return X', and
    VERIFY the proposal via verify_function_equivalence before returning it
    — this is the one pattern simple enough to hand-check without a general
    engine, everything else goes through simplify_function() instead, which
    doesn't need pattern-matching because Z3 already finds the reduction.
    """
    try:
        node = _find_function(code, func_name)
    except UnsupportedConstructError:
        return None

    if (len(node.body) == 1
            and isinstance(node.body[0], ast.If)
            and len(node.body[0].body) == 1
            and isinstance(node.body[0].body[0], ast.Return)
            and node.body[0].orelse
            and len(node.body[0].orelse) == 1
            and isinstance(node.body[0].orelse[0], ast.Return)):
        then_src = ast.dump(node.body[0].body[0].value)
        else_src = ast.dump(node.body[0].orelse[0].value)
        if then_src == else_src:
            candidate_body = ast.unparse(node.body[0].body[0])
            params = ", ".join(a.arg for a in node.args.args)
            candidate_code = f"def {func_name}({params}):\n    {candidate_body}\n"
            verification = verify_function_equivalence(code, func_name, candidate_code, func_name)
            return candidate_code, verification

    return None


def _prove_equal(a: Any, b: Any) -> EquivalenceResult:
    """Shared Z3 proof step: are `a` and `b` equal for all values of their
    free variables? (negate equality, check UNSAT)."""
    s = z3.Solver()
    s.set("timeout", _Z3_TIMEOUT_MS)
    try:
        s.add(a != b)
    except z3.Z3Exception as e:
        return EquivalenceResult(status="unsupported", reason=f"Z3 type mismatch: {e}")

    r = s.check()
    if r == z3.unsat:
        return EquivalenceResult(status="decided", equivalent=True)
    if r == z3.sat:
        try:
            m = s.model()
            decls = list(m.decls())
            if decls:
                cx = ", ".join(f"{d} = {m[d]}" for d in decls)
            else:
                cx = "any input (expressions differ unconditionally, e.g. by a constant)"
        except Exception:
            cx = "(counterexample unavailable)"
        return EquivalenceResult(status="decided", equivalent=False, counterexample=cx)
    return EquivalenceResult(status="unknown", reason="Z3 timeout")


__all__ = [
    "EquivalenceResult",
    "SimplificationResult",
    "UnsupportedConstructError",
    "verify_expression_equivalence",
    "verify_function_equivalence",
    "simplify_function",
    "propose_redundant_branch_removal",
]
