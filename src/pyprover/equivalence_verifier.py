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
  - Assignment to simple names: `x = <expr>`, `x: int = <expr>`, `x += <expr>`,
    `a = b = <expr>`, and tuple unpacking `a, b = <e1>, <e2>` (all right-hand
    sides are evaluated before any name is bound, so `a, b = b, a` swaps)
  - Integer powers with a literal exponent from 0 to MAX_POW_EXPONENT: `x ** 2`
    is rewritten to `x * x` before translation
  - Parameters annotated `bool` are Z3 Booleans, so `if flag:`, `not flag` and
    `flag and x > 0` work. Unannotated parameters are Int (see below)
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
control flow, multiple return values, float parameters (Python floats round,
so an equality proven over the reals need not hold for floats), and a bare
boolean used with and/or/not when its parameter is not annotated `bool`. The
reused `_expr_to_z3` seeds an unannotated name as a Z3 `Int`, so `not flag`
conflicts with `Not()`; annotate `flag: bool` or use an Int comparison (e.g.
`flag > 0`). Hitting any of these raises
`UnsupportedConstructError` with the specific construct named — this module
never silently produces a false "equivalent" or a wrong "simplified" result
for code it can't actually reason about. Compare
`pyprover/loop_verifier.py`'s own disclosed scope limits (INIT/PRESERVATION
only, no TERMINATION) — same honesty discipline, different feature.
"""

import ast
import copy
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
MAX_POW_EXPONENT = 16


class UnsupportedConstructError(ValueError):
    """Raised when code uses a construct outside this module's supported
    subset. Callers must treat this as 'cannot determine', never as
    'equivalent' or 'not equivalent' — see module docstring."""


class _PowExpander(ast.NodeTransformer):
    """Rewrite `x ** k` with a literal integer k in [0, MAX_POW_EXPONENT] as a
    product. Any other power is rejected rather than translated."""

    def visit_BinOp(self, node: ast.BinOp) -> ast.expr:
        self.generic_visit(node)
        if not isinstance(node.op, ast.Pow):
            return node
        k = node.right
        if not (isinstance(k, ast.Constant) and type(k.value) is int
                and 0 <= k.value <= MAX_POW_EXPONENT):
            raise UnsupportedConstructError(
                f"'**' is only supported with an integer literal exponent from 0 to {MAX_POW_EXPONENT}"
            )
        if k.value == 0:
            return ast.Constant(value=1)
        result = node.left
        for _ in range(k.value - 1):
            result = ast.BinOp(left=result, op=ast.Mult(), right=copy.deepcopy(node.left))
        return result


def _expr_to_z3_safe(node: ast.expr, env: Dict[str, Any]) -> Any:
    """Wraps the reused contract_verifier._expr_to_z3 to convert its raw
    NotImplementedError (its convention for "unsupported node type", e.g.
    function calls, attribute access) into this module's
    UnsupportedConstructError, so every caller in this file can catch one
    consistent exception type instead of two."""
    node = _PowExpander().visit(copy.deepcopy(node))
    node = _ContainerRewriter(env).visit(node)
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


def _is_bool_arg(arg: ast.arg) -> bool:
    """True if a parameter is annotated `bool` and so is a Z3 Boolean."""
    return isinstance(arg.annotation, ast.Name) and arg.annotation.id == "bool"


def _param_var(arg: ast.arg) -> Any:
    return z3.Bool(arg.arg) if _is_bool_arg(arg) else z3.Int(arg.arg)


# ---------------------------------------------------------------------------
# Containers: list[int] and dict[int, int] parameters, and list literals
#
# A list is a length (Int >= 0) and an element array (Int -> Int). A dict is
# a presence array (Int -> Bool) and a value array (Int -> Int). Only reads
# are modelled. Every read has an obligation that the solver must prove under
# the current path condition, so a value is only produced for inputs where
# Python would not raise IndexError or KeyError. A write, an alias, or a
# container used as a value is rejected. Writes would change the caller's
# object, and aliasing would make two names share one object, which a value
# model cannot represent.
# ---------------------------------------------------------------------------

_PATH_KEY = "<path>"      # Z3 Bool: the condition under which the current code runs
_COUNTER_KEY = "<counter>"  # next index for temporaries bound by _ContainerRewriter
_TEMP_PREFIX = "__c"       # temporaries; user names may not use this prefix


@dataclass(frozen=True)
class _Seq:
    length: Any  # Z3 Int
    items: Any   # Z3 Array(Int, Int)


@dataclass(frozen=True)
class _Map:
    present: Any  # Z3 Array(Int, Bool)
    values: Any   # Z3 Array(Int, Int)


_SORTS = {"int": z3.IntSort, "str": z3.StringSort, "bool": z3.BoolSort}
_DEFAULTS = {"int": lambda: z3.IntVal(0), "str": lambda: z3.StringVal(""),
             "bool": lambda: z3.BoolVal(False)}


def _sort_name(node: ast.expr) -> Optional[str]:
    return node.id if isinstance(node, ast.Name) and node.id in _SORTS else None


def _param_kind(arg: ast.arg) -> Any:
    """A hashable kind: "bool", "int", "str", ("list", elem) or ("dict", key, value)."""
    if _is_bool_arg(arg):
        return "bool"
    ann = arg.annotation
    if isinstance(ann, ast.Name) and ann.id in ("int", "str"):
        return ann.id
    if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
        base, sl = ann.value.id, ann.slice
        if base in ("list", "List") and _sort_name(sl):
            return ("list", _sort_name(sl))
        if (base in ("dict", "Dict") and isinstance(sl, ast.Tuple) and len(sl.elts) == 2
                and _sort_name(sl.elts[0]) in ("int", "str") and _sort_name(sl.elts[1])):
            return ("dict", _sort_name(sl.elts[0]), _sort_name(sl.elts[1]))
    return "int"  # unannotated parameters are Int, as before


def _make_param(kind: Any, name: str) -> Any:
    if kind == "bool":
        return z3.Bool(name)
    if kind == "str":
        return z3.String(name)
    if isinstance(kind, tuple) and kind[0] == "list":
        return _Seq(z3.Int(name + "__len"),
                    z3.Array(name + "__items", z3.IntSort(), _SORTS[kind[1]]()))
    if isinstance(kind, tuple) and kind[0] == "dict":
        key, val = _SORTS[kind[1]](), _SORTS[kind[2]]()
        return _Map(z3.Array(name + "__present", key, z3.BoolSort()),
                    z3.Array(name + "__values", key, val))
    return z3.Int(name)


def _input_assumptions(values: List[Any]) -> Any:
    """Conjunction of the input facts: every container length is non-negative."""
    facts = [v.length >= 0 for v in values if isinstance(v, _Seq)]
    return z3.And(*facts) if facts else z3.BoolVal(True)


def _path_of(env: Dict[str, Any]) -> Any:
    """The path condition: every container's length is non-negative, and the
    branch conditions taken so far all hold."""
    return env.get(_PATH_KEY, z3.BoolVal(True))


def _with_length_assumptions(env: Dict[str, Any]) -> None:
    lengths = [v.length >= 0 for v in env.values() if isinstance(v, _Seq)]
    base = env.get(_PATH_KEY, z3.BoolVal(True))
    env[_PATH_KEY] = z3.And(base, *lengths) if lengths else base


def _require(path: Any, cond: Any, what: str) -> None:
    """Raise unless `cond` holds on every input that reaches this point."""
    s = z3.Solver()
    s.set("timeout", _Z3_TIMEOUT_MS)
    s.add(path, z3.Not(cond))
    if s.check() != z3.unsat:
        raise UnsupportedConstructError(
            f"{what} may fail on some input that reaches it (not proven in range or present)"
        )


def _as_key_term(e: Any, sort: Any) -> Any:
    """An index or key as a Z3 term of `sort` (Int for lists, the key sort for dicts)."""
    if isinstance(e, bool):
        raise UnsupportedConstructError("container index or key has the wrong type")
    if isinstance(e, int) and sort == z3.IntSort():
        return z3.IntVal(e)
    if isinstance(e, z3.ExprRef) and e.sort() == sort:
        return e
    raise UnsupportedConstructError("container index or key has the wrong type")


class _ContainerRewriter(ast.NodeTransformer):
    """Replace container reads with temporaries bound to Z3 terms, and reject
    every other use of a container."""

    def __init__(self, env: Dict[str, Any]):
        self.env = env

    def _bind(self, value: Any) -> ast.Name:
        k = self.env.get(_COUNTER_KEY, 0)
        self.env[_COUNTER_KEY] = k + 1
        name = f"{_TEMP_PREFIX}{k}"
        self.env[name] = value
        node = ast.Name(id=name, ctx=ast.Load())
        node.is_temp = True  # marks it as generated, so visit_Name accepts it on a second pass
        return node

    def _container(self, node: ast.expr) -> Any:
        if isinstance(node, ast.Name) and isinstance(self.env.get(node.id), (_Seq, _Map)):
            return self.env[node.id]
        return None

    def visit_Name(self, node: ast.Name) -> ast.expr:
        if node.id.startswith(_TEMP_PREFIX) and not getattr(node, "is_temp", False):
            raise UnsupportedConstructError(f"name '{node.id}' is reserved")
        if isinstance(self.env.get(node.id), (_Seq, _Map)):
            raise UnsupportedConstructError(
                f"container '{node.id}' used as a value (only element reads, len() and "
                "'in' are modelled; aliasing and mutation are not)"
            )
        return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.expr:
        c = self._container(node.value)
        if c is None:
            return self.generic_visit(node)
        index = _expr_to_z3_safe(self.visit(node.slice), self.env)
        if isinstance(c, _Seq):
            i = _as_key_term(index, z3.IntSort())
            _require(_path_of(self.env), z3.And(-c.length <= i, i < c.length),
                     f"index into '{node.value.id}'")
            pos = z3.If(i < 0, i + c.length, i)  # Python's negative indexing
            return self._bind(z3.Select(c.items, pos))
        k = _as_key_term(index, c.present.domain())
        _require(_path_of(self.env), z3.Select(c.present, k), f"key into '{node.value.id}'")
        return self._bind(z3.Select(c.values, k))

    def _under(self, cond: Any, node: ast.expr) -> Any:
        """Translate `node` on the path where `cond` holds, then restore the path."""
        saved = _path_of(self.env)
        self.env[_PATH_KEY] = z3.And(saved, cond)
        try:
            return _expr_to_z3_safe(self.visit(node), self.env)
        finally:
            self.env[_PATH_KEY] = saved

    def visit_IfExp(self, node: ast.IfExp) -> ast.expr:
        cond = _expr_to_z3_safe(self.visit(node.test), self.env)
        if not isinstance(cond, z3.BoolRef):
            raise UnsupportedConstructError("conditional expression test must be a boolean")
        then_term = self._under(cond, node.body)
        else_term = self._under(z3.Not(cond), node.orelse)
        return self._bind(z3.If(cond, then_term, else_term))

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.expr:
        # Python evaluates `and`/`or` operands left to right and stops early, so
        # each operand is only reached on the path where the previous ones allow it.
        saved = _path_of(self.env)
        terms: List[Any] = []
        reach = saved
        try:
            for value in node.values:
                self.env[_PATH_KEY] = reach
                term = _expr_to_z3_safe(self.visit(value), self.env)
                terms.append(term)
                reach = z3.And(reach, term) if isinstance(node.op, ast.And) else z3.And(reach, z3.Not(term))
        finally:
            self.env[_PATH_KEY] = saved
        combined = z3.And(*terms) if isinstance(node.op, ast.And) else z3.Or(*terms)
        return self._bind(combined)

    def visit_Call(self, node: ast.Call) -> ast.expr:
        if (isinstance(node.func, ast.Name) and node.func.id == "len" and len(node.args) == 1
                and isinstance(node.args[0], ast.Name)):
            c = self._container(node.args[0])
            if isinstance(c, _Seq):
                return self._bind(c.length)
            if isinstance(c, _Map):
                raise UnsupportedConstructError("len() of a dict is not modelled")
        return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> ast.expr:
        if (len(node.ops) == 1 and isinstance(node.ops[0], (ast.In, ast.NotIn))
                and isinstance(self._container(node.comparators[0]), (_Seq, _Map))):
            c = self._container(node.comparators[0])
            if not isinstance(c, _Map):
                raise UnsupportedConstructError("'in' is only modelled for dict parameters")
            key = _as_key_term(_expr_to_z3_safe(self.visit(node.left), self.env), c.present.domain())
            present = z3.Select(c.present, key)
            return self._bind(present if isinstance(node.ops[0], ast.In) else z3.Not(present))
        return self.generic_visit(node)


def _as_z3_value(v: Any) -> Any:
    """Python literals from the translator (int, bool) as Z3 terms."""
    if isinstance(v, bool):
        return z3.BoolVal(v)
    if isinstance(v, int):
        return z3.IntVal(v)
    if isinstance(v, z3.ExprRef):
        return v
    raise UnsupportedConstructError(f"value of type {type(v).__name__} has no Z3 sort")


def _list_literal_value(node: ast.List, env: Dict[str, Any]) -> _Seq:
    values = [_as_z3_value(_expr_to_z3_safe(elt, env)) for elt in node.elts]
    if not values:
        raise UnsupportedConstructError("an empty list literal has no element sort to model")
    sort = values[0].sort()
    if sort not in (z3.IntSort(), z3.StringSort(), z3.BoolSort()):
        raise UnsupportedConstructError("list literal elements must be int, str or bool")
    default = {z3.IntSort(): z3.IntVal(0), z3.StringSort(): z3.StringVal(""),
               z3.BoolSort(): z3.BoolVal(False)}[sort]
    arr = z3.K(z3.IntSort(), default)
    for j, v in enumerate(values):
        if v.sort() != sort:
            raise UnsupportedConstructError("list literal elements must share one sort")
        arr = z3.Store(arr, z3.IntVal(j), v)
    return _Seq(z3.IntVal(len(values)), arr)


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

        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is None:
                continue  # a bare annotation binds nothing
            if not isinstance(stmt.target, ast.Name):
                raise UnsupportedConstructError(
                    "annotated assignment target must be a simple name"
                )
            env[stmt.target.id] = _expr_to_z3_safe(stmt.value, env)
            continue

        if isinstance(stmt, ast.Assign):
            if (len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
                    and isinstance(stmt.value, ast.List)):
                env[stmt.targets[0].id] = _list_literal_value(stmt.value, env)
                continue
            if all(isinstance(t, ast.Name) for t in stmt.targets):
                value = _expr_to_z3_safe(stmt.value, env)
                for t in stmt.targets:
                    env[t.id] = value
                continue
            if (len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Tuple)
                    and all(isinstance(t, ast.Name) for t in stmt.targets[0].elts)
                    and isinstance(stmt.value, ast.Tuple)
                    and len(stmt.value.elts) == len(stmt.targets[0].elts)):
                # Evaluate every right-hand side before binding any name.
                values = [_expr_to_z3_safe(v, env) for v in stmt.value.elts]
                for t, v in zip(stmt.targets[0].elts, values):
                    env[t.id] = v
                continue
            raise UnsupportedConstructError(
                "assignment must bind simple names, or unpack a tuple of the same length"
            )

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

            path = _path_of(env)
            then_env = dict(env)
            then_env[_PATH_KEY] = z3.And(path, cond)
            then_flow = _exec_stmts(stmt.body, then_env, max_unroll)

            else_env = dict(env)
            else_env[_PATH_KEY] = z3.And(path, z3.Not(cond))
            if stmt.orelse:
                else_flow = _exec_stmts(stmt.orelse, else_env, max_unroll)
            else:
                else_flow = ("fallthrough", else_env)

            if then_flow[0] == "return" and else_flow[0] == "return":
                return ("return", z3.If(cond, then_flow[1], else_flow[1]))

            if then_flow[0] == "fallthrough" and else_flow[0] == "fallthrough":
                merged: Dict[str, Any] = {}
                for name in set(then_env) | set(else_env):
                    if name.startswith("<") or name.startswith(_TEMP_PREFIX):
                        continue  # the path is restored below; temporaries are consumed
                    tv = then_env.get(name, env.get(name))
                    ev = else_env.get(name, env.get(name))
                    if tv is None or ev is None:
                        continue
                    if tv is ev:
                        merged[name] = tv
                    elif isinstance(tv, _Seq) and isinstance(ev, _Seq):
                        merged[name] = _Seq(z3.If(cond, tv.length, ev.length),
                                            z3.If(cond, tv.items, ev.items))
                    elif isinstance(tv, _Map) and isinstance(ev, _Map):
                        merged[name] = _Map(z3.If(cond, tv.present, ev.present),
                                            z3.If(cond, tv.values, ev.values))
                    elif isinstance(tv, (_Seq, _Map)) or isinstance(ev, (_Seq, _Map)):
                        raise UnsupportedConstructError(
                            f"container '{name}' is bound to different kinds on the two branches")
                    else:
                        merged[name] = z3.If(cond, tv, ev)
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
            env[arg.arg] = _make_param(_param_kind(arg), arg.arg)
    _with_length_assumptions(env)
    flow = _exec_stmts(list(func_node.body), env, max_unroll)
    if flow[0] != "return":
        raise UnsupportedConstructError(
            "function does not return a value on every path"
        )
    return _as_z3_value(flow[1])  # a constant-only body yields a Python literal


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

    kinds_a = [_param_kind(a) for a in node_a.args.args]
    kinds_b = [_param_kind(b) for b in node_b.args.args]
    if kinds_a != kinds_b:
        return EquivalenceResult(
            status="unsupported",
            reason=f"parameter types differ: {kinds_a} versus {kinds_b}",
        )
    shared_vars = [_make_param(kind, f"_arg{i}") for i, kind in enumerate(kinds_a)]
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

    result = _prove_equal(result_a, result_b, _input_assumptions(shared_vars))
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

    # Create the parameters here, so the input facts can be read back from them.
    env: Dict[str, Any] = {
        arg.arg: _make_param(_param_kind(arg), arg.arg) for arg in node.args.args
    }
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
    except (TypeError, ValueError, AttributeError) as e:
        # The translator was given a construct it does not model (e.g. a string
        # operator). That is "cannot determine", never a wrong answer.
        return SimplificationResult(
            status="unsupported",
            reason=f"construct could not be translated: {type(e).__name__}: {e}",
        )

    try:
        simplified = z3.simplify(original)
    except Exception as e:
        return SimplificationResult(status="unsupported", reason=f"Z3 simplify() failed: {e}")

    original_str = str(original)
    simplified_str = str(simplified)
    assumption = _input_assumptions(list(env.values()))

    # Z3 also reorders terms, e.g. "100 + a*50" becomes "100 + 50*a", which is
    # not a simplification. Only a result with fewer nodes is reported.
    if original_str == simplified_str or _z3_size(simplified) >= _z3_size(original):
        return SimplificationResult(status="already_simplest", original_expr=original_str)

    # Safety net: the rewrite is only reported if the solver confirms it is
    # equal to the original for every input. Anything else is not a simplification.
    proof = _prove_equal(original, simplified, assumption)
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


def _prove_equal(a: Any, b: Any, assume: Any = None) -> EquivalenceResult:
    """Shared Z3 proof step: are `a` and `b` equal for all values of their
    free variables that satisfy `assume` (negate equality, check UNSAT)?"""
    s = z3.Solver()
    s.set("timeout", _Z3_TIMEOUT_MS)
    if assume is not None:
        s.add(assume)
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
