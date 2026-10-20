"""PyProver Phase 2 - Contract verification using Z3 solver"""
import ast
import copy
import re
from typing import Dict, List, Any, Optional, Set, Tuple
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
# Key that marks an evaluation environment as one where object attributes are modelled.
MODEL_ATTRIBUTES = "__model_attributes__"
# Key that marks an evaluation environment where all(...)/any(...) over range(...) become
# ForAll/Exists. Loop invariants need the quantified terms; clause checks handle quantified
# clauses separately (quantifiers.py), so they leave this unset and see no change.
MODEL_QUANTIFIERS = "__model_quantifiers__"


class ContractInputTooLargeError(ValueError):
    """Raised when input code exceeds the size this verifier will scan."""


_DECORATOR_CONTRACT_RE = re.compile(
    r"@(requires|ensures|loop_invariant)\s*\(\s*((?:(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')\s*)+)\)",
    re.DOTALL,
)
_STRING_PIECE_RE = re.compile(r"\"((?:[^\"\\]|\\.)*)\"|'((?:[^'\\]|\\.)*)'")


def _decorator_clauses(code: str) -> List[Tuple[str, str]]:
    """Read ``@requires("...")``, ``@ensures("...")`` and ``@loop_invariant("...")``.

    The argument may be several adjacent string literals split across lines, as in
    the v13 layout that the old single-line extractor missed. Works in any language,
    since it only looks for the decorator text.
    """
    found: List[Tuple[str, str]] = []
    for match in _DECORATOR_CONTRACT_RE.finditer(code):
        kind, pieces = match.group(1), match.group(2)
        text = "".join(a if a or not b else b for a, b in _STRING_PIECE_RE.findall(pieces)).strip()
        if text:
            found.append((kind, text))
    return found


# Bounds that keep inlining finite. Over-budget or over-long loops are unproven.
_MAX_UNROLL = 16         # iterations a constant range() loop may be unrolled into
_MAX_STATEMENTS = 2000   # statements executed across all paths, counting branch duplication
_PURE_CALLS = frozenset({"len", "abs", "min", "max"})


class _Unmodelled(Exception):
    """A body construct the inliner cannot express as one expression."""


def _inlined_return_expr(code: str) -> Optional[ast.expr]:
    """Return the function's result as one expression over its parameters.

    Modelled: ``name = expr`` and ``name: T = expr``, ``if``/``else`` (each path
    runs to its own return, merged as a conditional expression), ``for`` over a
    constant ``range()`` (unrolled up to ``_MAX_UNROLL`` iterations), ``pass``,
    docstrings, and calls to pure builtins used as statements. Anything else,
    including ``while``, subscript or attribute writes, other calls as statements,
    and paths that fall off the end, returns None so ``result`` is not proven.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if len(funcs) != 1:
        return None
    try:
        return _run(funcs[0].body, {}, [0])
    except _Unmodelled:
        return None


def _run(stmts: List[ast.stmt], bindings: Dict[str, ast.expr], budget: List[int]) -> ast.expr:
    """Symbolically run ``stmts`` and return the expression for the value returned."""
    for index, stmt in enumerate(stmts):
        budget[0] += 1
        if budget[0] > _MAX_STATEMENTS:
            raise _Unmodelled("too many statements across branches")
        rest = stmts[index + 1:]
        if isinstance(stmt, ast.Return):
            if stmt.value is None:
                raise _Unmodelled("bare return")
            return _inline_names(stmt.value, bindings)
        if isinstance(stmt, ast.Pass) or _is_pure_statement(stmt):
            continue
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise _Unmodelled("write to a non-name target")
            bindings[stmt.targets[0].id] = _inline_names(stmt.value, bindings)
            continue
        if isinstance(stmt, ast.AnnAssign):
            if not isinstance(stmt.target, ast.Name) or stmt.value is None:
                raise _Unmodelled("annotation without a name target or value")
            bindings[stmt.target.id] = _inline_names(stmt.value, bindings)
            continue
        if isinstance(stmt, ast.If):
            test = _inline_names(stmt.test, bindings)
            then_expr = _run(stmt.body + rest, dict(bindings), budget)
            else_expr = _run(stmt.orelse + rest, dict(bindings), budget)
            return ast.IfExp(test=test, body=then_expr, orelse=else_expr)
        if isinstance(stmt, ast.For):
            return _run(_unroll(stmt) + rest, bindings, budget)
        raise _Unmodelled(type(stmt).__name__)
    raise _Unmodelled("a path ends without a return")


def _is_pure_statement(stmt: ast.stmt) -> bool:
    """Docstrings and calls to pure builtins have no effect, so they can be skipped."""
    if not isinstance(stmt, ast.Expr):
        return False
    value = stmt.value
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return True
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in _PURE_CALLS
    )


def _unroll(loop: ast.For) -> List[ast.stmt]:
    """Expand ``for v in range(<int constants>)`` into one assignment and body per value."""
    if loop.orelse or not isinstance(loop.target, ast.Name):
        raise _Unmodelled("loop with else or a non-name target")
    call = loop.iter
    if not (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "range"
        and not call.keywords
        and 1 <= len(call.args) <= 3
    ):
        raise _Unmodelled("only range() loops are unrolled")
    bounds = []
    for arg in call.args:
        if not (isinstance(arg, ast.Constant) and type(arg.value) is int):
            raise _Unmodelled("range() bound is not an integer constant")
        bounds.append(arg.value)
    try:
        values = list(range(*bounds))
    except ValueError:
        raise _Unmodelled("range() step is zero")
    if len(values) > _MAX_UNROLL:
        raise _Unmodelled(f"range() loop longer than {_MAX_UNROLL} iterations")
    unrolled: List[ast.stmt] = []
    for value in values:
        unrolled.append(ast.Assign(
            targets=[ast.Name(id=loop.target.id, ctx=ast.Store())],
            value=ast.Constant(value=value),
        ))
        unrolled.extend(loop.body)
    return unrolled


class _NameInliner(ast.NodeTransformer):
    def __init__(self, bindings: Dict[str, ast.expr]):
        self.bindings = bindings

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if isinstance(node.ctx, ast.Load) and node.id in self.bindings:
            return ast.copy_location(copy.deepcopy(self.bindings[node.id]), node)
        return node


def _inline_names(expr: ast.expr, bindings: Dict[str, ast.expr]) -> ast.expr:
    """Copy ``expr`` with every bound name replaced by its bound expression."""
    if not bindings:
        return expr
    return _NameInliner(bindings).visit(copy.deepcopy(expr))


def _substitute_result(clause: str, return_text: str) -> str:
    """Replace each result alias in a postcondition with the return expression.

    Textual substitution, so builtins such as ``len(result)`` see the expression
    too, not only bare names.
    """
    pattern = r"\b(?:" + "|".join(sorted(_RESULT_ALIASES)) + r")\b"
    return re.sub(pattern, f"({return_text})", clause)


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


def _length_const(name: str, env: Dict[str, Any]) -> Any:
    """The Z3 symbol for len(name), the same one a clause's len(name) uses."""
    return z3_builtins.try_call_to_z3(ast.parse(f"len({name})", mode="eval").body, env, _expr_to_z3)


def normalized_index(index: Any, length: Any) -> Any:
    """Python's negative indexing: arr[-1] is arr[len(arr) - 1]."""
    return z3.If(index < 0, index + length, index)


def _mentions_result(clause: str) -> bool:
    return any(alias in clause.lower() for alias in _RESULT_ALIASES)


def _numeric_operands(node: ast.AST) -> Set[str]:
    """Names used directly as an operand of arithmetic or a comparison."""
    if isinstance(node, ast.BinOp):
        operands = [node.left, node.right]
    elif isinstance(node, ast.UnaryOp):
        operands = [node.operand]
    elif isinstance(node, ast.Compare):
        operands = [node.left, *node.comparators]
    else:
        return set()
    return {operand.id for operand in operands if isinstance(operand, ast.Name)}


def _valueless_bare_params(code: str, clauses: List[str]) -> Set[str]:
    """Parameters the result passes through bare, with no sign they are numbers.

    The inliner treats a bare parameter as a number. That is right when the code or a
    clause uses it in arithmetic or a comparison. It is wrong for a list or object
    that is only returned or copied, as in ``return arr`` with ``Pre: len(arr) > 0``.
    A postcondition that compares ``result`` with a value is taken as evidence that
    the result is numeric. Such parameters make the result unjudgeable.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if len(funcs) != 1:
        return set()
    func = funcs[0]
    params = {a.arg for a in func.args.args}
    passed: Set[str] = set()
    numeric: Set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name):
            passed.add(node.value.id)
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Name):
            passed.add(node.value.id)
        numeric |= _numeric_operands(node)
    result_is_numeric = False
    result_is_sequence = False
    for clause in clauses:
        try:
            expr = ast.parse(clause, mode="eval").body
        except SyntaxError:
            continue
        for node in ast.walk(expr):
            operands = _numeric_operands(node)
            numeric |= operands
            if operands & _RESULT_ALIASES:
                result_is_numeric = True
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "len"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in _RESULT_ALIASES
            ):
                result_is_sequence = True
    if result_is_numeric:
        numeric |= passed
    if result_is_sequence:
        # len(result) only makes sense for a sequence, so a returned parameter is not a number.
        return set()
    return (passed & params) - numeric


def _expr_to_z3(node: ast.expr, env: Dict[str, Any]) -> Any:
    """Recursively convert an AST expression node to a Z3 expression."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return z3.BoolVal(node.value)
        if isinstance(node.value, int):
            return node.value
        if isinstance(node.value, float):
            return z3.RealVal(node.value)  # exact decimal value, e.g. 0.1 is 1/10
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
        if isinstance(node.op, ast.Div):
            # Python's / is always real division. Z3's Int / is integer division.
            # Z3 leaves x / 0 unspecified, while Python raises, so a divisor that is not
            # a non-zero literal is not translated: the clause is left unchecked.
            if not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, (int, float))
                    and node.right.value != 0):
                raise NotImplementedError("division by a value that may be zero")
            return _as_real(left) / _as_real(right)
        if isinstance(node.op, (ast.FloorDiv, ast.Mod)) and (_is_real(left) or _is_real(right)):
            # Python floor and modulo on floats are not Z3 real operations; skip the clause.
            raise NotImplementedError("floor division and modulo are not defined over reals here")
        if isinstance(node.op, (ast.FloorDiv, ast.Mod)) and not (
                isinstance(node.right, ast.Constant) and type(node.right.value) is int
                and node.right.value > 0):
            # Z3's div/mod are Euclidean and differ from Python for negative or symbolic
            # divisors (Python 7 % -2 == -1, Z3 mod(7, -2) == 1). Only a positive literal is safe.
            raise NotImplementedError(
                "'//' and '%' are only supported with a positive integer literal divisor")
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
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Name) and isinstance(env.get(node.value.id), z3.ArrayRef):
            index = _expr_to_z3(node.slice, env)
            if isinstance(index, int) and not isinstance(index, bool):
                index = z3.IntVal(index)
            length = _length_const(node.value.id, env)
            return z3.Select(env[node.value.id], normalized_index(index, length))
        raise NotImplementedError("subscript of a value that is not a parameter array")
    if isinstance(node, ast.Attribute):
        # Only the verifiers that model object state set this marker, so other
        # users of the shared evaluator still treat attribute access as unsupported.
        if env.get(MODEL_ATTRIBUTES) and isinstance(node.value, ast.Name):
            key = f"{node.value.id}.{node.attr}"
            if key not in env:
                env[key] = z3.Int(f"{node.value.id}__{node.attr}")
            return env[key]
        raise NotImplementedError("attribute of a value that is not a name")
    if isinstance(node, ast.IfExp):
        test = _expr_to_z3(node.test, env)
        if isinstance(test, bool):
            test = z3.BoolVal(test)
        then_val = _expr_to_z3(node.body, env)
        else_val = _expr_to_z3(node.orelse, env)
        if _is_real(then_val) or _is_real(else_val):
            then_val, else_val = _as_real(then_val), _as_real(else_val)
        return z3.If(test, then_val, else_val)
    if isinstance(node, ast.Call):
        if (env.get(MODEL_QUANTIFIERS) and isinstance(node.func, ast.Name)
                and node.func.id in ("all", "any") and len(node.args) == 1
                and isinstance(node.args[0], ast.GeneratorExp)):
            return _quantifier_to_z3(node.func.id, node.args[0], env)
        result = z3_builtins.try_call_to_z3(node, env, _expr_to_z3)
        if result is not None:
            return result
        raise NotImplementedError(f"Unsupported call: {ast.dump(node.func)}")
    raise NotImplementedError(f"Unsupported AST node: {type(node).__name__}")


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


def _is_real(e: Any) -> bool:
    """True if e is a Z3 Real expression (python floats count as real)."""
    return isinstance(e, float) or (isinstance(e, z3.ArithRef) and e.is_real())


def _as_real(e: Any) -> Any:
    """Convert a python number or Z3 Int expression to a Z3 Real expression."""
    if isinstance(e, bool):
        return e
    if isinstance(e, (int, float)):
        return z3.RealVal(e)
    if isinstance(e, z3.ArithRef) and e.is_int():
        return z3.ToReal(e)
    return e


def _has_float_literal(tree: ast.AST) -> bool:
    return any(isinstance(n, ast.Constant) and isinstance(n.value, float) for n in ast.walk(tree))


def float_annotated_params(code: str) -> List[str]:
    """Names of parameters annotated ``float`` in any function defined in code."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [
        arg.arg
        for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        for arg in node.args.args
        if isinstance(arg.annotation, ast.Name) and arg.annotation.id == "float"
    ]


def seed_real_env(clauses: List[str], env: Dict[str, Any], float_params: List[str] = ()) -> None:
    """Create Real-sorted variables before any clause is translated.

    A name is Real if it is in float_params, or if it appears in a clause that
    contains a float literal. Variables are created on first use otherwise, as
    Int, so this must run first. Real is the right model for floats: anything
    proven over the reals also holds for every float input.
    """
    real_names = set(float_params)
    for clause in clauses:
        try:
            tree = ast.parse(clause.strip(), mode="exec")
        except SyntaxError:
            continue
        if _has_float_literal(tree):
            real_names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for name in real_names:
        if name not in env and name not in ("True", "False"):
            env[name] = z3.Real(name)


def _conditional_parts(clause: str) -> Optional[Tuple[ast.expr, ast.expr]]:
    """Split ``if <cond>: <clause>`` into (cond, clause) AST nodes.

    Only the single-statement form without ``else`` counts. Anything else
    returns None, so ordinary expressions are parsed as before.
    """
    try:
        module = ast.parse(clause.strip(), mode="exec")
    except SyntaxError:
        return None
    if len(module.body) != 1 or not isinstance(module.body[0], ast.If):
        return None
    node = module.body[0]
    if node.orelse or len(node.body) != 1 or not isinstance(node.body[0], ast.Expr):
        return None
    return node.test, node.body[0].value


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
        parts = _conditional_parts(clause)
        if parts is not None:
            cond_node, then_node = parts
            cond = _expr_to_z3(cond_node, env)
            then = _expr_to_z3(then_node, env)
            if not (_is_z3_bool(cond) and _is_z3_bool(then)):
                return None
            return z3.Implies(cond, then)
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

        for kind, text in _decorator_clauses(code):
            if kind == "requires":
                spec.preconditions.append(text)
            elif kind == "ensures":
                spec.postconditions.append(text)
            else:
                spec.invariants.append(text)

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
        # Nothing was checked, so nothing is proven. Reporting True here would
        # make an unannotated function read as VERIFIED.
        if not all_clauses:
            result["verified"] = False
            result["inconclusive"] = True
            result["details"].append("INCONCLUSIVE: no contract annotations found (add # Pre: / # Post: comments)")
            return result

        if not Z3_AVAILABLE:
            # Structural check only: confirm clauses are non-empty strings. That is
            # not a proof, so it cannot report verified.
            result["verified"] = False
            result["inconclusive"] = True
            result["details"].append(
                "Z3 not available — structural check only (install z3-solver for full verification)"
            )
            result["details"].append(
                f"Found {len(contract.preconditions)} precondition(s), "
                f"{len(contract.postconditions)} postcondition(s), "
                f"{len(contract.invariants)} invariant(s)"
            )
            return result

        return_node = _inlined_return_expr(code)
        return_text = ast.unparse(return_node) if return_node is not None else None
        return_src = [return_text] if return_text else []
        env: Dict[str, Any] = {MODEL_ATTRIBUTES: True}
        seed_real_env(all_clauses + return_src, env, float_annotated_params(code))
        z3_builtins.seed_string_env(
            contract.preconditions + contract.postconditions + contract.invariants + return_src, env,
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
        post_unproven: List[str] = []
        valueless = _valueless_bare_params(
            code, contract.preconditions + contract.postconditions + contract.invariants
        )

        # Bodies the inliner cannot express (loops, array writes) go to the
        # verification-condition model. That import is local because loop_vc
        # builds on this module.
        loop_verdicts = None
        if return_text is None and any(_mentions_result(c) for c in contract.postconditions):
            from . import loop_vc
            loop_verdicts = loop_vc.check_result_clauses(
                code,
                [c for c in contract.postconditions if _mentions_result(c)],
                contract.preconditions,
                float_annotated_params(code),
            )

        for clause in contract.postconditions:
            references_result = _mentions_result(clause)
            if references_result and valueless:
                post_unproven.append(clause)
                result["details"].append(
                    f"  Post '{clause}' — not proven (returns {', '.join(sorted(valueless))} "
                    "as a value, with no sign that it is a number)"
                )
                continue
            if references_result:
                # Substitute the function's own return expression for ``result`` and
                # check it like any other postcondition.
                if return_text is None:
                    verdict, detail = (loop_verdicts or {}).get(clause, ("unknown", None))
                    if verdict == "yes":
                        post_verified += 1
                        result["details"].append(f"  Post '{clause}' — implied by preconditions (loop model) ✓")
                    else:
                        post_unproven.append(clause)
                        if verdict == "no":
                            note = f" (the loop model finds a counterexample, which may not be reachable: {detail})"
                        else:
                            note = f" ({detail})" if detail else " (no single return expression, and the loop model cannot judge it)"
                        result["details"].append(f"  Post '{clause}' — not proven{note}")
                    continue
                z3_expr = _clause_to_z3(_substitute_result(clause, return_text), env)
            else:
                z3_expr = _clause_to_z3(clause, env)

            if z3_expr is None:
                post_unproven.append(clause)
                result["details"].append(f"  Post '{clause}' — skipped (non-arithmetic), not proven")
                continue
            # A constant clause such as ``5 >= 0`` folds to a Python bool, which the solver calls reject.
            if isinstance(z3_expr, bool):
                z3_expr = z3.BoolVal(z3_expr)

            # Preconditions must imply the postcondition. A postcondition that
            # mentions result is checked with the return expression substituted in.
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
                post_unproven.append(clause)
                result["details"].append(
                    f"  Post '{clause}' — Z3 timeout (kept as unverified)"
                )

        if post_fails:
            result["verified"] = False
            result["postconditions_ok"] = False
            for f in post_fails:
                result["details"].append(f"FAIL: {f}")
        elif post_unproven:
            # Not a failure, but not proven either. A pass needs proof.
            result["verified"] = False
            result["inconclusive"] = True
            result["details"].append(
                f"INCONCLUSIVE: {len(post_unproven)} postcondition(s) not proven"
            )
        elif contract.postconditions:
            result["details"].append(f"✓ Postconditions: {post_verified} verified")

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
