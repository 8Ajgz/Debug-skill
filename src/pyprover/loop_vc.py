"""PyProver verification conditions for loops and array writes.

contract_verifier inlines a body into one expression over its parameters. That
cannot express state that changes across iterations, or an array that is written
and then read. This module runs the body over an explicit state instead:

- Branches run separately, and the state after an ``if`` is merged with ``z3.If``.
  Every assignment is guarded by the path condition, and a ``return`` records a
  sink with its guard.
- ``while`` loops need a ``# Invariant:`` comment on the lines directly above them.
  The standard rule applies: the invariant holds on entry; the body preserves it,
  with the loop's variables havoc'd and the condition assumed; and after the loop
  the invariant holds with the condition false.
- ``for x in arr`` becomes an index loop over ``arr``, with an implicit invariant
  ``0 <= i <= len(arr)``. ``for x in range(...)`` with symbolic bounds becomes an
  index loop too. Constant ranges are unrolled instead.
- Array writes become ``z3.Store``. Each array is a parameter with a symbolic
  length, and negative indices are normalised as Python does. Reads past the end
  are left unconstrained, which over-approximates.

Anything outside this fragment raises _Unmodelled and the postcondition stays
unproven. A counterexample from this model is never reported as a failure,
because havoc and index bounds can produce states that no real run reaches.
"""
import ast
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import z3

from . import contract_verifier as cv

_INVARIANT_RE = re.compile(r"^\s*#\s*(?:Invariant|Inv)\s*:\s*(.+?)\s*$")
_ARRAY_INDEX_INVARIANT = "0 <= {idx} and {idx} <= len({arr})"


class _Unmodelled(Exception):
    """The body uses a construct this module does not model."""


@dataclass
class _Context:
    lines: List[str]
    containers: Set[str]
    premises: List[Any] = field(default_factory=list)
    # (description, formula, premises in force when the obligation arose)
    obligations: List[Tuple[str, Any, List[Any]]] = field(default_factory=list)
    sinks: List[Tuple[Any, Any]] = field(default_factory=list)
    loop_depth: int = 0
    fresh: int = 0

    def fresh_name(self, stem: str) -> str:
        self.fresh += 1
        return f"__{stem}{self.fresh}"


def check_result_clauses(
    code: str,
    clauses: List[str],
    pre_clauses: List[str],
    float_params: List[str],
) -> Optional[Dict[str, Tuple[str, Optional[str]]]]:
    """Judge postconditions on ``result`` for a body with loops or array writes.

    Returns ``{clause: (verdict, detail)}`` where verdict is "yes", "no" or
    "unknown". "no" means the model found a counterexample, which may be spurious,
    so callers must not treat it as a failed proof. Returns None when the body is
    outside the modelled fragment.
    """
    try:
        return _check(code, clauses, pre_clauses, float_params)
    except (_Unmodelled, cv._Unmodelled, NotImplementedError, z3.Z3Exception,
            ValueError, TypeError, KeyError, AttributeError, SyntaxError):
        return None


def _check(code, clauses, pre_clauses, float_params):
    tree = ast.parse(code)
    funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if len(funcs) != 1:
        raise _Unmodelled("expected exactly one function")
    func = funcs[0]
    args = func.args
    if args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs:
        raise _Unmodelled("unsupported parameter kinds")
    params = [a.arg for a in args.args]
    ctx = _Context(lines=code.splitlines(), containers=_find_containers(func, params))

    env: Dict[str, Any] = {}
    for p in params:
        if p in ctx.containers:
            env[p] = z3.Array(p, z3.IntSort(), z3.IntSort())
        elif p in float_params:
            env[p] = z3.Real(p)
        else:
            env[p] = z3.Int(p)
    for c in ctx.containers:
        ctx.premises.append(cv._length_const(c, env) >= 0)
    for text in pre_clauses:
        part = cv._clause_to_z3(text, dict(env))
        if part is not None and cv._is_z3_bool(part):
            ctx.premises.append(part)

    st, live = _exec(func.body, dict(env), z3.BoolVal(True), ctx)
    if not z3.is_false(z3.simplify(live)):
        raise _Unmodelled("a path can end without a return")

    # An obligation may rely only on premises established before it, in program
    # order. A loop's exit premise is justified by that loop's own obligations, so
    # using it there would be circular and would make a wrong invariant look valid.
    failed = [
        desc for desc, formula, premises in ctx.obligations
        if cv._check_implied(premises, formula)[0] != "yes"
    ]
    if failed:
        note = "loop invariant not established: " + "; ".join(failed)
        return {clause: ("unknown", note) for clause in clauses}
    return {clause: _judge(clause, env, ctx) for clause in clauses}


def _judge(clause, env, ctx):
    if not ctx.sinks:
        return ("unknown", None)
    verdicts = []
    for guard, value in ctx.sinks:
        post_env = dict(env)
        for alias in cv._RESULT_ALIASES:
            post_env[alias] = value
        post = cv._clause_to_z3(clause, post_env)
        if post is None or not cv._is_z3_bool(post):
            return ("unknown", None)
        verdicts.append(cv._check_implied(ctx.premises + [guard], post))
    for verdict, cx in verdicts:
        if verdict == "no":
            return ("no", cx)
    if all(verdict == "yes" for verdict, _ in verdicts):
        return ("yes", None)
    return ("unknown", None)


# ---------------------------------------------------------------------------
# Containers: parameters that are subscripted or iterated over
# ---------------------------------------------------------------------------

def _find_containers(func: ast.AST, params: List[str]) -> Set[str]:
    nodes = list(ast.walk(func))
    parents: Dict[ast.AST, ast.AST] = {}
    for node in nodes:
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    candidates: Set[str] = set()
    writes = False
    for node in nodes:
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            candidates.add(node.value.id)
            if isinstance(node.ctx, ast.Store):
                writes = True
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Name):
            candidates.add(node.iter.id)
    if not candidates <= set(params):
        raise _Unmodelled("subscript or iteration over a name that is not a parameter")
    if writes and len(candidates) > 1:
        # Two names can refer to the same list, so a write through one may change
        # what the other reads. Without alias analysis that is not modelled.
        raise _Unmodelled("array write while another array is accessed (possible aliasing)")

    for node in nodes:
        if isinstance(node, ast.Name) and node.id in candidates:
            parent = parents.get(node)
            allowed = (
                (isinstance(parent, ast.Subscript) and parent.value is node)
                or (isinstance(parent, ast.For) and parent.iter is node)
                or (
                    isinstance(parent, ast.Call)
                    and isinstance(parent.func, ast.Name)
                    and parent.func.id == "len"
                    and len(parent.args) == 1
                    and parent.args[0] is node
                )
            )
            if not allowed:
                raise _Unmodelled(f"bare use of array '{node.id}'")
    return candidates


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

def _exec(stmts: List[ast.stmt], st: Dict[str, Any], live: Any, ctx: _Context):
    """Run ``stmts`` from state ``st`` under path condition ``live``.

    Returns the state and the condition under which execution falls through to the
    end of ``stmts`` (False once a return has been reached on this path).
    """
    for stmt in stmts:
        if isinstance(stmt, ast.Return):
            if ctx.loop_depth:
                raise _Unmodelled("return inside a loop")
            if stmt.value is None:
                raise _Unmodelled("bare return")
            ctx.sinks.append((live, _eval(stmt.value, st)))
            return st, z3.BoolVal(False)
        pair = _assignment(stmt)
        if pair is not None:
            target, value_node = pair
            st = _assign(target, _eval(value_node, st), st, live, ctx)
            continue
        if isinstance(stmt, ast.Pass) or cv._is_pure_statement(stmt):
            continue
        if isinstance(stmt, ast.If):
            test = _as_bool(_eval(stmt.test, st))
            then_st, then_live = _exec(stmt.body, dict(st), z3.And(live, test), ctx)
            else_st, else_live = _exec(stmt.orelse, dict(st), z3.And(live, z3.Not(test)), ctx)
            st = _merge(test, then_st, else_st, st)
            live = z3.If(test, then_live, else_live)
            continue
        if isinstance(stmt, ast.While):
            st = _exec_while(stmt.test, stmt.body, _loop_invariants(stmt, ctx), st, live, ctx)
            continue
        if isinstance(stmt, ast.For):
            st, live = _exec_for(stmt, st, live, ctx)
            continue
        raise _Unmodelled(f"{type(stmt).__name__} is not modelled")
    return st, live


def _assignment(stmt: ast.stmt) -> Optional[Tuple[ast.expr, ast.expr]]:
    """Return (target, value) for plain, annotated and augmented assignments."""
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        return stmt.targets[0], stmt.value
    if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        return stmt.target, stmt.value
    if isinstance(stmt, ast.AugAssign):
        return stmt.target, ast.BinOp(left=_as_load(stmt.target), op=stmt.op, right=stmt.value)
    return None


def _as_load(target: ast.expr) -> ast.expr:
    if isinstance(target, ast.Name):
        return ast.Name(id=target.id, ctx=ast.Load())
    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
        return ast.Subscript(value=ast.Name(id=target.value.id, ctx=ast.Load()),
                             slice=target.slice, ctx=ast.Load())
    raise _Unmodelled("augmented assignment to an unsupported target")


def _assign(target, value, st, live, ctx):
    value = _as_z3(value)
    if isinstance(target, ast.Name):
        old = st.get(target.id)
        if old is None:
            old = z3.FreshConst(value.sort(), target.id)
        st[target.id] = _ite(live, value, old)
        return st
    if (
        isinstance(target, ast.Subscript)
        and isinstance(target.value, ast.Name)
        and target.value.id in ctx.containers
    ):
        base = target.value.id
        index = _normalized_index(target.slice, st, base)
        st[base] = _ite(live, z3.Store(st[base], index, value), st[base])
        return st
    raise _Unmodelled("write to an unsupported target")


def _merge(test, then_st, else_st, base):
    merged = {}
    for name in set(then_st) | set(else_st):
        a = then_st.get(name, base.get(name))
        b = else_st.get(name, base.get(name))
        if a is None:
            merged[name] = b
        elif b is None:
            merged[name] = a
        else:
            merged[name] = _ite(test, a, b)
    return merged


def _exec_while(test, body, invariants, st, live, ctx):
    if not invariants:
        raise _Unmodelled("loop without a # Invariant: comment")
    modified = _assigned_names(body)

    def invariant(state):
        parts = []
        for text in invariants:
            part = cv._clause_to_z3(text, state)
            if part is None or not cv._is_z3_bool(part):
                raise _Unmodelled(f"invariant not expressible: {text}")
            parts.append(part)
        return z3.And(*parts)

    ctx.obligations.append(
        ("loop invariant holds on entry", z3.Implies(live, invariant(st)), list(ctx.premises))
    )

    head = _havoc(st, modified)
    cond = _as_bool(_eval(test, head))
    head_inv = invariant(head)
    ctx.loop_depth += 1
    try:
        body_st, _ = _exec(body, dict(head), cond, ctx)
    finally:
        ctx.loop_depth -= 1
    ctx.obligations.append((
        "loop invariant is preserved by the body",
        z3.Implies(z3.And(head_inv, cond), invariant(body_st)),
        list(ctx.premises),
    ))

    after = _havoc(st, modified)
    exit_cond = _as_bool(_eval(test, after))
    ctx.premises.append(z3.Implies(live, z3.And(invariant(after), z3.Not(exit_cond))))
    return after


def _exec_for(stmt: ast.For, st, live, ctx):
    if stmt.orelse or not isinstance(stmt.target, ast.Name):
        raise _Unmodelled("for loop with else or a non-name target")
    target = stmt.target.id
    it = stmt.iter

    if isinstance(it, ast.Name) and it.id in ctx.containers:
        invariants = _loop_invariants(stmt, ctx)
        if not invariants:
            raise _Unmodelled("loop without a # Invariant: comment")
        idx = ctx.fresh_name("i")
        loop = ast.While(
            test=ast.Compare(
                left=_name(idx),
                ops=[ast.Lt()],
                comparators=[ast.Call(func=_name("len"), args=[_name(it.id)], keywords=[])],
            ),
            body=[
                ast.Assign(
                    targets=[_name(target, store=True)],
                    value=ast.Subscript(value=_name(it.id), slice=_name(idx), ctx=ast.Load()),
                ),
                *stmt.body,
                ast.AugAssign(target=_name(idx, store=True), op=ast.Add(), value=ast.Constant(1)),
            ],
            orelse=[],
        )
        loop._pyprover_invariants = invariants + [_ARRAY_INDEX_INVARIANT.format(idx=idx, arr=it.id)]
        init = [ast.Assign(targets=[_name(idx, store=True)], value=ast.Constant(0))]
        return _exec(init + [loop], st, live, ctx)

    if (
        isinstance(it, ast.Call)
        and isinstance(it.func, ast.Name)
        and it.func.id == "range"
        and not it.keywords
        and 1 <= len(it.args) <= 3
    ):
        try:
            return _exec(cv._unroll(stmt), st, live, ctx)
        except cv._Unmodelled:
            pass
        invariants = _loop_invariants(stmt, ctx)
        if not invariants:
            raise _Unmodelled("loop without a # Invariant: comment")
        args = it.args
        start = args[0] if len(args) >= 2 else ast.Constant(0)
        stop = args[1] if len(args) >= 2 else args[0]
        step = args[2] if len(args) == 3 else ast.Constant(1)
        if not (isinstance(step, ast.Constant) and type(step.value) is int and step.value > 0):
            raise _Unmodelled("range() step is not a positive integer constant")
        stop_name = ctx.fresh_name("stop")
        idx = ctx.fresh_name("i")
        loop = ast.While(
            test=ast.Compare(left=_name(idx), ops=[ast.Lt()], comparators=[_name(stop_name)]),
            body=[
                ast.Assign(targets=[_name(target, store=True)], value=_name(idx)),
                *stmt.body,
                ast.AugAssign(target=_name(idx, store=True), op=ast.Add(), value=step),
            ],
            orelse=[],
        )
        loop._pyprover_invariants = invariants
        init = [
            ast.Assign(targets=[_name(stop_name, store=True)], value=stop),
            ast.Assign(targets=[_name(idx, store=True)], value=start),
        ]
        return _exec(init + [loop], st, live, ctx)

    raise _Unmodelled("only for loops over an array parameter or range() are modelled")


def _name(identifier: str, store: bool = False) -> ast.Name:
    return ast.Name(id=identifier, ctx=ast.Store() if store else ast.Load())


def _loop_invariants(stmt: ast.stmt, ctx: _Context) -> List[str]:
    """Invariants from ``# Invariant:`` comments directly above the loop, in order."""
    explicit = getattr(stmt, "_pyprover_invariants", None)
    if explicit is not None:
        return list(explicit)
    found = []
    row = stmt.lineno - 2
    while row >= 0 and ctx.lines[row].lstrip().startswith("#"):
        match = _INVARIANT_RE.match(ctx.lines[row])
        if match:
            found.append(match.group(1))
        row -= 1
    return list(reversed(found))


def _assigned_names(stmts: List[ast.stmt]) -> Set[str]:
    """Names a loop body can change: assignment targets, loop targets, and array bases."""
    names: Set[str] = set()
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets = [node.target]
            elif isinstance(node, ast.For):
                targets = [node.target]
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
                elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                    names.add(target.value.id)
    return names


def _havoc(st: Dict[str, Any], names: Set[str]) -> Dict[str, Any]:
    out = dict(st)
    for name in names:
        sort = st[name].sort() if name in st else z3.IntSort()
        out[name] = z3.FreshConst(sort, name)
    return out


# ---------------------------------------------------------------------------
# Expressions and sorts
# ---------------------------------------------------------------------------

def _eval(node: ast.expr, st: Dict[str, Any]):
    return _as_z3(cv._expr_to_z3(node, st))


def _as_z3(value):
    if isinstance(value, bool):
        return z3.BoolVal(value)
    if isinstance(value, int):
        return z3.IntVal(value)
    if isinstance(value, float):
        return z3.RealVal(value)
    return value


def _as_bool(value):
    value = _as_z3(value)
    if z3.is_bool(value):
        return value
    raise _Unmodelled("condition is not a boolean expression")


def _ite(cond, a, b):
    a, b = _as_z3(a), _as_z3(b)
    if a.sort() != b.sort():
        if cv._is_real(a) or cv._is_real(b):
            a, b = cv._as_real(a), cv._as_real(b)
        else:
            raise _Unmodelled("branches produce values of different sorts")
    return z3.If(cond, a, b)


def _normalized_index(index_node: ast.expr, st, base: str):
    index = _eval(index_node, st)
    return cv.normalized_index(index, cv._length_const(base, st))
