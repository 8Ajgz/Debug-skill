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

CLASS AND CALL MODELS: a parameter or a field annotated with a class the
analysed file can reach (the same file, or one it imports from this repository,
see project_index.py) is read as an object. Its scalar and container fields are
symbols, and it is read-only: a method that writes a field is not inlined. An
Enum subclass with distinct literal members is a finite value, compared by
identity with its members. A call to a function or method is inlined by
symbolically executing its body with the arguments bound, if the body is pure
(no field writes), not recursive, undecorated, and returns on every path.
Properties are calls with no arguments. A method or field that a subclass may
override is not read, because the subclass's version could run instead. Subclasses
are found by base-class name: in the repository with a ProjectScope, and in the
analysed code alone without one (the domain records that assumption).

NOT SUPPORTED, HONESTLY, NOT SILENTLY: calls that write fields, calls to
built-in methods (list.append, str.join), constructors, keyword arguments,
recursion, unbounded or nested loops, mutation of aliased objects, generators,
exceptions as control flow, multiple return values, float parameters (Python floats round,
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

from .contract_verifier import _expr_to_z3, _OP_MAP, _as_real
from .project_index import base_name as _name_of, module_bool_flags, subclass_members as _subclass_members

_Z3_TIMEOUT_MS = 5000
DEFAULT_MAX_UNROLL = 64
MAX_POW_EXPONENT = 16
MAX_CALL_DEPTH = 8  # calls nested inside calls, each inlined into its caller


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
    node = _FieldRewriter(env).visit(node)
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
_FACTS_KEY = "<facts>"      # shared list of Z3 facts (and notes) that restrict the verified domain
_TRY_KEY = "<try>"          # the failure cells of the innermost enclosing try block
_TYPE_NOTE = "arguments have the types their annotations state"
_FLOAT_NOTE = "floats are treated as exact real numbers, without rounding"
_BOOL_NOTE = "unannotated parameters used as conditions are taken to be bool"
_TRY_NOTE = "inputs that raise an exception the handler does not catch are excluded"
_EXITS_KEY = "<exits>"      # list of (path, field state) recorded at each return, for methods
_WRITES_NOTE = "only the returned value is simplified; field writes are not part of the result"
_RAISE_NOTE = "inputs that reach a raise statement are excluded"
_RANGE_NOTE = "loops over range(n) are exact for n at most the unroll bound"
_ENUM_NOTE = "an enum value is shown as the index of its member"
_TYPE_TEST_NOTE = ("a test of an opaque value's type is an unknown truth value, which is not related "
                   "to the tests of other types, so a counterexample that depends on one is not reported")
_CLOSED_NOTE = ("a class's methods and fields are taken to be its own, since no subclass is in the "
                "analysed code; pass a ProjectScope to check the repository")


_EXPRESSION_KEY = "<expression>"  # set for standalone expressions, whose free names are variables
_MODELLED_BUILTINS = frozenset({"abs", "min", "max", "len", "isinstance", "range"})
_SCOPE_KEY = "<scope>"            # the scope that resolves the class and function names the code uses
_CALL_STACK_KEY = "<calls>"       # names of the functions being inlined, outermost first
_MAX_UNROLL_KEY = "<max_unroll>"  # the loop bound, which an inlined call uses too


class _Opaque:
    """A name bound by an import. Its value is not modelled, so any use is rejected."""


_OPAQUE = _Opaque()


@dataclass(frozen=True)
class _Opt:
    """An Optional[T] parameter: a flag for None, and the value when it is not None."""
    isnone: Any  # Z3 Bool
    value: Any   # Z3 term of T


class _Unbound:
    """A name that may or may not be bound after a loop. Reading it is rejected."""


_UNBOUND = _Unbound()


@dataclass(frozen=True)
class _Seq:
    length: Any  # Z3 Int
    items: Any   # Z3 Array(Int, Int)
    opaque: bool = False  # elements are Any values: the array is a placeholder, never read


@dataclass(frozen=True)
class _Map:
    present: Any  # Z3 Array(Int, Bool)
    values: Any   # Z3 Array(Int, Int)
    opaque: bool = False  # values are Any values: the array is a placeholder, never read


@dataclass(frozen=True)
class _AnyValue:
    """A value of type Any: an arbitrary Python object, of which nothing is known. It can be
    passed on unchanged, and tested against None (through the _Opt that holds it). Any
    other use of it, such as an attribute, an operator, or equality, is not modelled."""
    name: str


@dataclass(frozen=True)
class _Enum:
    """A value of a plain Enum class, as an index into its members. The index is in
    [0, number of members), a domain fact recorded wherever the value is created."""
    classdef: ast.ClassDef
    term: Any  # Z3 Int, or the index of a member


@dataclass
class _Record:
    """A dataclass instance built by a constructor call, as the value of each declared field.

    A dataclass compares by its fields, so two records are equal exactly when every field
    is equal (see _same_result). A record is immutable here: it is returned, bound to a
    name, and read field by field, but no statement writes to it."""
    classdef: ast.ClassDef
    fields: Dict[str, Any]

    def __str__(self) -> str:
        return f"{self.classdef.name}({', '.join(f'{k}={v}' for k, v in self.fields.items())})"


class _LocalScope:
    """The classes and functions defined at the top level of the analysed file only.
    A name the file imports is not resolved, so anything that names it is not modelled."""

    def __init__(self, code: str):
        tree = ast.parse(code)
        self._classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        self._functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        self._all_classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        self._flags = module_bool_flags(tree)

    def is_module_flag(self, name: str) -> bool:
        return name in self._flags

    def class_def(self, name: str) -> Optional[ast.ClassDef]:
        return self._classes.get(name)

    def function_def(self, name: str) -> Optional[ast.FunctionDef]:
        return self._functions.get(name)

    def subclass_members(self, classdef: ast.ClassDef) -> set:
        """Names that subclasses in the analysed code define. Subclasses elsewhere are not seen."""
        return _subclass_members(self._all_classes, classdef.name)


def _base_name(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _enum_members(classdef: ast.ClassDef) -> Optional[Dict[str, int]]:
    """Member name -> index, for a plain Enum subclass whose members are distinct int or
    str literals. None for anything else: an Enum whose values could alias, a bool or
    other literal value, or a member computed by a call (such as auto())."""
    if len(classdef.bases) != 1 or _base_name(classdef.bases[0]) != "Enum":
        return None
    members: Dict[str, int] = {}
    values: List[str] = []
    for stmt in classdef.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue  # docstring
        if isinstance(stmt, ast.FunctionDef):
            continue  # a method is not a member; calling one on a member is not modelled
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and not stmt.targets[0].id.startswith("_")
                and isinstance(stmt.value, ast.Constant)
                and type(stmt.value.value) in (int, str)):
            members[stmt.targets[0].id] = len(members)
            values.append(repr(stmt.value.value))
            continue
        return None
    if not members or len(set(values)) != len(values):
        return None
    return members


def _annotation_class(annotation: ast.expr, scope: Any) -> Optional[ast.ClassDef]:
    """The class an annotation names in the scope, or None. A string annotation is read
    as the name it spells."""
    if scope is None:
        return None
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            annotation = ast.parse(annotation.value, mode="eval").body
        except SyntaxError:
            return None
    return scope.class_def(annotation.id) if isinstance(annotation, ast.Name) else None


_SORTS = {"int": z3.IntSort, "str": z3.StringSort, "bool": z3.BoolSort, "float": z3.RealSort}
_DEFAULTS = {"int": lambda: z3.IntVal(0), "str": lambda: z3.StringVal(""), "float": lambda: z3.RealVal(0),
             "bool": lambda: z3.BoolVal(False)}


def _is_any_annotation(node: ast.expr) -> bool:
    """`Any`, or `typing.Any`."""
    return (isinstance(node, ast.Name) and node.id == "Any") or (
        isinstance(node, ast.Attribute) and node.attr == "Any")


def _sort_name(node: ast.expr) -> Optional[str]:
    return node.id if isinstance(node, ast.Name) and node.id in _SORTS else None


def _param_kind(arg: ast.arg, body: Optional[List[ast.stmt]] = None, scope: Any = None) -> Any:
    """A hashable kind: "bool", "int", "float", "str", ("list", elem),
    ("dict", key, value), ("opt", base), ("enum", classdef) or ("obj", classdef).
    An unannotated parameter is an int.

    A class named by the annotation, in `scope`, is ("enum", classdef) for a plain
    Enum and ("obj", classdef) for any other class (see the class models above).
    Any other annotation is not modelled. If the function body never reads the
    parameter, its type cannot change the result, so it is kind "unused". If the
    body does read it, the annotation is rejected rather than read as an int."""
    if arg.annotation is None:
        if body is not None and _used_as_condition(body, arg.arg):
            return "bool"  # inferred from use; see _BOOL_NOTE
        return "int"
    if _is_bool_arg(arg):
        return "bool"
    ann = arg.annotation
    if isinstance(ann, ast.Name) and ann.id in ("int", "str", "float"):
        return ann.id
    if _is_any_annotation(ann):
        # An Any value is opaque, so a parameter the body never reads cannot change the result.
        return "any" if body is None or _reads_name(body, arg.arg) else "unused"
    if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
        base, sl = ann.value.id, ann.slice
        if base in ("list", "List") and (_sort_name(sl) or _is_any_annotation(sl)):
            return ("list", _sort_name(sl) or "any")
        if (base in ("dict", "Dict") and isinstance(sl, ast.Tuple) and len(sl.elts) == 2
                and _sort_name(sl.elts[0]) in ("int", "str")
                and (_sort_name(sl.elts[1]) or _is_any_annotation(sl.elts[1]))):
            return ("dict", _sort_name(sl.elts[0]), _sort_name(sl.elts[1]) or "any")
        if base == "Optional" and _is_any_annotation(sl):
            return "any"
        if base == "Optional" and _sort_name(sl) in ("int", "str", "bool", "float"):
            return ("opt", _sort_name(sl))
    if (isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr)):
        sides = [ann.left, ann.right]
        none_sides = [x for x in sides if isinstance(x, ast.Constant) and x.value is None]
        base_sides = [x for x in sides if _sort_name(x)]
        if len(none_sides) == 1 and len(base_sides) == 1:
            return ("opt", _sort_name(base_sides[0]))
    named = _annotation_class(ann, scope)
    if named is not None:
        return ("enum", named) if _enum_members(named) is not None else ("obj", named)
    if body is not None and not _reads_name(body, arg.arg):
        return "unused"
    return _opaque_kind(ann)


def _opaque_kind(ann: ast.expr) -> Any:
    """The kind of a value whose type is not modelled. Such a value is opaque: the model
    knows nothing about it, and every use that depends on what it is, such as an attribute,
    an operator, or equality, is rejected where it occurs. So a value of an unmodelled type
    is modelled soundly as an Any value, with two differences: a non-Optional type is never
    None, and a container of unmodelled elements is a list or dict of Any values."""
    if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
        base, sl = ann.value.id, ann.slice
        if base in ("list", "List"):
            return ("list", "any")
        if base in ("dict", "Dict") and isinstance(sl, ast.Tuple) and len(sl.elts) == 2 \
                and _sort_name(sl.elts[0]) in ("int", "str"):
            return ("dict", _sort_name(sl.elts[0]), "any")
        if base == "Optional":
            return "any"  # may be None, as Any may
    return "opaque"


def _used_as_condition(body: List[ast.stmt], name: str) -> bool:
    """True if the name is used as a truth value: `not x`, `x and y`, `if x:`, `x if c else y`."""
    def is_name(n: Any) -> bool:
        return isinstance(n, ast.Name) and n.id == name
    for n in ast.walk(ast.Module(body=list(body), type_ignores=[])):
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not) and is_name(n.operand):
            return True
        if isinstance(n, ast.BoolOp) and any(is_name(v) for v in n.values):
            return True
        if isinstance(n, (ast.If, ast.While, ast.IfExp, ast.Assert)) and is_name(n.test):
            return True
    return False


def _inferred_bool_params(func_node: ast.FunctionDef) -> List[str]:
    return [a.arg for a in func_node.args.args
            if a.annotation is None and _used_as_condition(func_node.body, a.arg)]


def _reads_name(body: List[ast.stmt], name: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == name
               for n in ast.walk(ast.Module(body=list(body), type_ignores=[])))


def _element_sort(name: str) -> Any:
    """The Z3 sort of container elements. An Any element has a placeholder sort, which no
    read uses (reads of an opaque container are rejected)."""
    return z3.IntSort() if name == "any" else _SORTS[name]()


def _make_param(kind: Any, name: str, facts: Optional[List[Any]] = None, scope: Any = None) -> Any:
    """The symbolic value of a parameter of this kind. An enum or an object needs
    `facts` (its domain is recorded there) and, for an object, the `scope` its class
    is read in."""
    if isinstance(kind, tuple) and kind[0] in ("enum", "obj") and facts is None:
        raise UnsupportedConstructError("internal: a class-typed value needs a facts list")
    if isinstance(kind, tuple) and kind[0] == "enum":
        count = len(_enum_members(kind[1]) or {})
        facts.append(z3.And(z3.Int(name) >= 0, z3.Int(name) < count))
        facts.append(_ENUM_NOTE)
        return _Enum(kind[1], z3.Int(name))
    if isinstance(kind, tuple) and kind[0] == "obj":
        return _class_object(kind[1], f"{name}.", scope, facts)
    if kind == "unused":
        return z3.Int(name)  # never read, so its value does not matter
    if kind == "any":
        # Any may be None, so the value is an _Opt whose None flag is a Z3 Bool.
        return _Opt(z3.Bool(name + "__none"), _AnyValue(name + "__val"))
    if kind == "opaque":
        # A value of an unmodelled, non-Optional type: never None.
        return _Opt(z3.BoolVal(False), _AnyValue(name + "__val"))
    if kind == "bool":
        return z3.Bool(name)
    if kind == "str":
        return z3.String(name)
    if kind == "float":
        return z3.Real(name)
    if isinstance(kind, tuple) and kind[0] == "opt":
        return _Opt(z3.Bool(name + "__none"), _make_param(kind[1], name + "__val"))
    if isinstance(kind, tuple) and kind[0] == "list":
        return _Seq(z3.Int(name + "__len"),
                    z3.Array(name + "__items", z3.IntSort(), _element_sort(kind[1])),
                    opaque=kind[1] == "any")
    if isinstance(kind, tuple) and kind[0] == "dict":
        key, val = _SORTS[kind[1]](), _element_sort(kind[2])
        return _Map(z3.Array(name + "__present", key, z3.BoolSort()),
                    z3.Array(name + "__values", key, val),
                    opaque=kind[2] == "any")
    return z3.Int(name)


def _assume_of(facts: List[Any]) -> Any:
    """The Z3 facts among `facts` (domain notes are strings and are skipped)."""
    return z3.And(*[f for f in facts if not isinstance(f, str)]) if facts else z3.BoolVal(True)


def _notes_of(facts: List[Any]) -> Optional[str]:
    """The domain restrictions recorded in `facts`, as one readable phrase."""
    seen: List[str] = []
    for f in facts:
        if isinstance(f, str) and f not in seen:
            seen.append(f)
    return "; ".join(seen) if seen else None


def _input_assumptions(values: List[Any]) -> Any:
    """Conjunction of the input facts: every container length is non-negative."""
    facts = [v.length >= 0 for v in values if isinstance(v, _Seq)]
    return z3.And(*facts) if facts else z3.BoolVal(True)


def _merge_envs(cond: Any, then_env: Dict[str, Any], else_env: Dict[str, Any],
                base: Dict[str, Any]) -> Dict[str, Any]:
    """The bindings after `if cond` in which each name takes its then- or else-value."""
    merged: Dict[str, Any] = {}
    for name in set(then_env) | set(else_env):
        if name.startswith("<") or name.startswith(_TEMP_PREFIX):
            continue  # the path is restored by the caller; temporaries are consumed
        tv = then_env.get(name, base.get(name))
        ev = else_env.get(name, base.get(name))
        if tv is None or ev is None:
            continue
        if tv is ev:
            merged[name] = tv
        elif isinstance(tv, _Unbound) or isinstance(ev, _Unbound):
            merged[name] = _UNBOUND
        elif isinstance(tv, _Opaque) or isinstance(ev, _Opaque):
            merged[name] = _OPAQUE
        elif isinstance(tv, _Opt) and isinstance(ev, _Opt) and isinstance(tv.value, _AnyValue):
            if tv.value != ev.value:
                raise UnsupportedConstructError(f"'{name}' is an Any value that the two branches bind differently")
            merged[name] = _Opt(z3.If(cond, tv.isnone, ev.isnone), tv.value)
        elif isinstance(tv, _Opt) and isinstance(ev, _Opt):
            merged[name] = _Opt(z3.If(cond, tv.isnone, ev.isnone), z3.If(cond, tv.value, ev.value))
        elif isinstance(tv, _Seq) and isinstance(ev, _Seq) and tv.opaque == ev.opaque:
            merged[name] = _Seq(z3.If(cond, tv.length, ev.length), z3.If(cond, tv.items, ev.items), tv.opaque)
        elif isinstance(tv, _Map) and isinstance(ev, _Map) and tv.opaque == ev.opaque:
            merged[name] = _Map(z3.If(cond, tv.present, ev.present), z3.If(cond, tv.values, ev.values), tv.opaque)
        elif isinstance(tv, _Enum) and isinstance(ev, _Enum) and tv.classdef is ev.classdef:
            merged[name] = _Enum(tv.classdef, z3.If(cond, tv.term, ev.term))
        elif isinstance(tv, _Record) and isinstance(ev, _Record) and tv.classdef is ev.classdef:
            merged[name] = _select(cond, tv, ev)
        elif isinstance(tv, (_Seq, _Map)) or isinstance(ev, (_Seq, _Map)):
            raise UnsupportedConstructError(
                f"container '{name}' is bound to different kinds on the two branches")
        else:
            merged[name] = z3.If(cond, _as_z3_value(tv), _as_z3_value(ev))
    return merged


def _list_source(node: ast.expr, env: Dict[str, Any]) -> Optional[Tuple["_Seq", str]]:
    """The list an iterable names, with the name its elements are keyed by, or None.

    A list-valued name, or a list field of an object (bound on first use, as a field read
    binds it). Anything else, such as a call that returns a list, is not a list the model
    knows: iterating it could raise, which the loop model would not show."""
    if isinstance(node, ast.Name):
        value = env.get(node.id)
        return (value, node.id) if isinstance(value, _Seq) else None
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        obj = env.get(node.value.id)
        kind = obj.fields.get(node.attr) if isinstance(obj, _ObjRef) else None
        if isinstance(kind, tuple) and kind[0] == "list" and node.attr not in obj.methods:
            key = f"{obj.prefix}{node.attr}"
            if key not in env:
                env[key] = obj.value(node.attr)
            return (env[key], key)
    return None


def _is_container_loop(stmt: ast.For, env: Dict[str, Any]) -> bool:
    """`for x in xs`, `for i, x in enumerate(xs)` or `for i in range(len(xs))` where xs is a
    list parameter, literal, or list field of an object."""
    it = stmt.iter
    if isinstance(it, (ast.Name, ast.Attribute)):
        return _list_source(it, env) is not None
    if _is_enumerate(it):
        return _list_source(it.args[0], env) is not None
    return (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range"
            and len(it.args) == 1 and isinstance(it.args[0], ast.Call)
            and isinstance(it.args[0].func, ast.Name) and it.args[0].func.id == "len"
            and len(it.args[0].args) == 1 and _list_source(it.args[0].args[0], env) is not None)


def _is_symbolic_range(stmt: ast.For) -> bool:
    """`for i in range(n)` or `for i in range(a, n)` where the bound n is not a literal."""
    it = stmt.iter
    if not (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range"
            and isinstance(stmt.target, ast.Name)):
        return False
    if len(it.args) not in (1, 2):
        return False
    if len(it.args) == 2 and not (isinstance(it.args[0], ast.Constant) and type(it.args[0].value) is int):
        return False
    bound = it.args[-1]
    return not isinstance(bound, ast.Constant) and not (
        isinstance(bound, ast.Call) and isinstance(bound.func, ast.Name) and bound.func.id == "len")


def _unroll_symbolic_range(stmt: ast.For, env: Dict[str, Any], max_unroll: int) -> Dict[str, Any]:
    """Unroll a loop over range(a, n) with a symbolic n. Iteration j runs only where j < n,
    which is exact for every n at most a + max_unroll. Larger n is outside the domain,
    and the domain records that."""
    if stmt.orelse:
        raise UnsupportedConstructError("for ... else is not supported")
    target = stmt.target.id
    target_was_bound = target in env and not isinstance(env[target], _Unbound)
    start = stmt.iter.args[0].value if len(stmt.iter.args) == 2 else 0
    bound = _as_z3_value(_expr_to_z3_safe(stmt.iter.args[-1], env))
    if not (isinstance(bound, z3.ArithRef) and bound.is_int()):
        raise UnsupportedConstructError("range() bound must be an integer")
    facts = env.setdefault(_FACTS_KEY, [])
    facts.append(bound <= start + max_unroll)
    facts.append(_RANGE_NOTE)
    before = set(env)
    current = env
    for k in range(max_unroll):
        j = start + k
        guard = z3.IntVal(j) < bound
        iter_env = dict(current)
        iter_env[_PATH_KEY] = z3.And(_path_of(current), guard)
        iter_env[target] = j
        flow = _exec_stmts(list(stmt.body), iter_env, max_unroll)
        if flow[0] != "fallthrough":
            raise UnsupportedConstructError("'return' or 'raise' inside a loop body is not supported")
        new_names = {n for n in flow[1]
                     if not n.startswith("<") and not n.startswith(_TEMP_PREFIX)} - before - {target}
        if new_names:
            raise UnsupportedConstructError(
                f"variable(s) {sorted(new_names)} first bound inside a range loop may be unbound after it")
        current = {**current, **_merge_envs(guard, flow[1], current, current)}
    if not target_was_bound:
        current[target] = _UNBOUND
    return current


def _is_enumerate(node: ast.expr) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "enumerate"
            and len(node.args) == 1 and not node.keywords)


def _loop_names(stmt: ast.For, indexed: bool) -> List[str]:
    """The names a loop binds: one name, or the (index, element) pair of an enumerate."""
    if not indexed and isinstance(stmt.target, ast.Name):
        return [stmt.target.id]
    if indexed and isinstance(stmt.target, ast.Tuple) and len(stmt.target.elts) == 2 and all(
            isinstance(e, ast.Name) for e in stmt.target.elts):
        return [e.id for e in stmt.target.elts]
    raise UnsupportedConstructError(
        "loop variable must be a simple name, or an (index, element) pair for enumerate")


def _unroll_container_loop(stmt: ast.For, env: Dict[str, Any], max_unroll: int) -> Dict[str, Any]:
    """Unroll a loop over a container whose length is symbolic.

    Iteration k runs only where the length exceeds k, so the result is exact for
    every list of length at most `max_unroll`. Longer lists are not covered, and
    the loop records the fact `length <= max_unroll` so every claim that uses this
    loop is stated for that domain only.

    The loop takes `x in xs` (the element), `i in range(len(xs))` (the index), or
    `i, x in enumerate(xs)` (both).
    """
    if stmt.orelse:
        raise UnsupportedConstructError("for ... else is not supported")
    if _is_enumerate(stmt.iter):
        seq, list_name = _list_source(stmt.iter.args[0], env) or (None, None)
        if seq is None:
            raise UnsupportedConstructError("enumerate is only modelled over a list parameter, literal or field")
        indexed, element = True, True
    elif isinstance(stmt.iter, (ast.Name, ast.Attribute)):
        seq, list_name = _list_source(stmt.iter, env)
        indexed, element = False, True  # the target takes seq.items[k]
    else:
        seq, list_name = _list_source(stmt.iter.args[0].args[0], env)
        indexed, element = False, False  # the target takes the index k, which uses the length alone
    names = _loop_names(stmt, indexed)
    bound_before = {n: n in env and not isinstance(env[n], _Unbound) for n in names}

    facts = env.setdefault(_FACTS_KEY, [])
    facts.append(seq.length <= max_unroll)
    facts.append(f"lists of length at most {max_unroll}")
    before = set(env)
    current = env
    for k in range(max_unroll):
        guard = seq.length > k
        iter_env = dict(current)
        iter_env[_PATH_KEY] = z3.And(_path_of(current), guard)
        if seq.opaque:
            # An element of an opaque list is an opaque value named for its index, so it is
            # the same value in every use within the iteration (see _element_value).
            element_value = _element_value(list_name, k)
            if indexed:
                iter_env[names[0]] = z3.IntVal(k)
                iter_env[names[1]] = element_value
            else:
                iter_env[names[0]] = element_value if element else z3.IntVal(k)
        elif indexed:
            iter_env[names[0]] = z3.IntVal(k)
            iter_env[names[1]] = z3.Select(seq.items, z3.IntVal(k))
        else:
            iter_env[names[0]] = z3.Select(seq.items, z3.IntVal(k)) if element else z3.IntVal(k)
        flow = _exec_stmts(list(stmt.body), iter_env, max_unroll)
        if flow[0] != "fallthrough":
            raise UnsupportedConstructError("'return' inside a loop body is not supported")
        new_names = {n for n in flow[1]
                     if not n.startswith("<") and not n.startswith(_TEMP_PREFIX)} - before - set(names)
        if new_names:
            raise UnsupportedConstructError(
                f"variable(s) {sorted(new_names)} first bound inside a container loop "
                "may be unbound after it")
        merged = _merge_envs(guard, flow[1], current, current)
        if seq.opaque:
            for n in names:
                merged.pop(n, None)  # each iteration binds its own element value
        current = {**current, **merged}
    for n in names:
        if seq.opaque or not bound_before[n]:
            # Python leaves the target bound only if the list is non-empty, and which element
            # is last is not known for an opaque list.
            current[n] = _UNBOUND
    return current


def _element_value(list_name: str, index: int) -> "_Opt":
    """The value of element `index` of a list of Any values: optional, as Any may be None."""
    return _Opt(z3.Bool(f"{list_name}[{index}]__none"), _AnyValue(f"{list_name}[{index}]"))


def _unroll_literal_loop(stmt: ast.For, env: Dict[str, Any], max_unroll: int) -> Dict[str, Any]:
    """Unroll a loop over a tuple or list literal, which has a known number of elements.

    As in Python, the elements are evaluated once, before the first iteration, and the
    target takes each in turn. After a loop over a non-empty literal the target keeps its
    last value.
    """
    if stmt.orelse:
        raise UnsupportedConstructError("for ... else is not supported")
    names = _loop_names(stmt, False)
    if len(stmt.iter.elts) > max_unroll:
        raise UnsupportedConstructError(f"loop over {len(stmt.iter.elts)} literal elements exceeds max_unroll")
    values = [_as_z3_value(_expr_to_z3_safe(e, env)) for e in stmt.iter.elts]
    bound_before = names[0] in env and not isinstance(env[names[0]], _Unbound)
    current = env
    for value in values:
        iter_env = dict(current)
        iter_env[names[0]] = value
        flow = _exec_stmts(list(stmt.body), iter_env, max_unroll)
        if flow[0] != "fallthrough":
            raise UnsupportedConstructError("'return' inside a loop body is not supported")
        current = flow[1]
    if not values and not bound_before:
        current[names[0]] = _UNBOUND
    return current


class _ObjRef:
    """An object whose fields are read through names `<prefix><attr>` in the environment.

    The `self` of a method (prefix "self__") and a parameter annotated with a class
    (prefix "<param>.") are both read this way. Each field is a symbol fixed for the
    whole call. A method's self may be written, but only where `is_self` is set, and
    a call that writes fields is not inlined. A parameter object is never written,
    so no statement can change a field between two reads.

    `cache` is shared between the two sides of an equivalence check, so both sides
    see the same field values. `methods` and `properties` are the names the class
    defines once; a name defined twice (a property with a setter, say) is left out,
    so calling it is not modelled.
    """

    def __init__(self, fields: Dict[str, Any], cache: Dict[str, Any], facts: List[Any],
                 prefix: str = "self__", classdef: Optional[ast.ClassDef] = None,
                 scope: Any = None, is_self: Optional[bool] = None):
        self.fields = fields
        self.cache = cache
        self.facts = facts
        self.prefix = prefix
        self.classdef = classdef
        self.scope = scope
        self.is_self = prefix == "self__" if is_self is None else is_self
        self.label = "self" if self.is_self else prefix.rstrip(".")
        # A subclass may override these names, so reading one here could run its code instead.
        self.overridable: set = set()
        if classdef is not None and scope is not None:
            self.overridable = scope.subclass_members(classdef)
            if isinstance(scope, _LocalScope):
                facts.append(_CLOSED_NOTE)
        defs = [f for f in (classdef.body if classdef is not None else [])
                if isinstance(f, ast.FunctionDef)]
        counts = {f.name: 0 for f in defs}
        for f in defs:
            counts[f.name] += 1
        once = [f for f in defs if counts[f.name] == 1]
        self.methods: Dict[str, ast.FunctionDef] = {f.name: f for f in once}
        self.properties = {f.name for f in once if any(
            isinstance(d, ast.Name) and d.id == "property" for d in f.decorator_list)}

    def kind(self, attr: str) -> Any:
        kind = self.fields.get(attr)
        if kind is None:
            raise UnsupportedConstructError(f"field '{self.label}.{attr}' has no modelled type")
        if isinstance(kind, str) and kind.startswith("!"):
            raise UnsupportedConstructError(kind[1:])
        if isinstance(kind, tuple) and kind[0] == "obj":
            raise UnsupportedConstructError(
                f"field '{self.label}.{attr}' holds an object, and nested objects are not modelled")
        return kind

    def value(self, attr: str) -> Any:
        kind = self.kind(attr)
        if attr not in self.cache:
            term = _make_param(kind, f"{self.prefix}{attr}", self.facts, self.scope)
            self.cache[attr] = term
            if isinstance(term, _Seq):
                self.facts.append(term.length >= 0)
        return self.cache[attr]


# A name for the object of a method, kept so that code and tests written for self still read the same.
_SelfRef = _ObjRef


def _class_object(classdef: ast.ClassDef, prefix: str, scope: Any, facts: List[Any]) -> _ObjRef:
    """A read-only object of a project class, whose field symbols start with `prefix`."""
    return _ObjRef(_class_fields(classdef, scope), {}, facts, prefix=prefix, classdef=classdef, scope=scope)


_SCALAR_FIELD_KINDS = ("int", "bool", "str", "float")


def _self_name_of(func_node: ast.FunctionDef) -> Optional[str]:
    return func_node.args.args[0].arg if func_node.args.args else None


def _attributes_on(body: List[ast.stmt], name: str) -> set:
    """Every attribute the body reads or writes through the name `name`."""
    return {n.attr for n in ast.walk(ast.Module(body=list(body), type_ignores=[]))
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == name}


def _self_attributes(func_node: ast.FunctionDef, self_name: str) -> set:
    """Every field the body reads or writes through `self`."""
    return _attributes_on(func_node.body, self_name)


def _writes_fields(func_node: ast.FunctionDef, self_name: str) -> bool:
    return any(isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
               and isinstance(n.value, ast.Name) and n.value.id == self_name
               for n in ast.walk(ast.Module(body=list(func_node.body), type_ignores=[])))


def _self_ref_in(env: Dict[str, Any]) -> Optional["_ObjRef"]:
    return next((v for v in env.values() if isinstance(v, _ObjRef) and v.is_self), None)


def _final_field(exits: List[Any], attr: str, initial: Any) -> Any:
    """The value of field `attr` when the method returns: the value recorded at the
    return that runs, chosen by each return's path. The paths of returns are disjoint."""
    key = f"self__{attr}"
    vals = [(path, state[key]) for path, state in exits if key in state]
    if not vals:
        return initial
    result = vals[-1][1]
    for path, value in reversed(vals[:-1]):
        result = z3.If(path, value, result)
    return result


def _annotation_kind(annotation: ast.expr, scope: Any = None) -> Any:
    """The kind of a field from its annotation, or the reason it is not modelled."""
    try:
        return _param_kind(ast.arg(arg="_", annotation=annotation), body=None, scope=scope)
    except UnsupportedConstructError:
        return f"!field annotation not modelled: {ast.unparse(annotation)}"


def _literal_kind(value: ast.expr) -> Any:
    """The kind of a field assigned a literal, or None when the value is not a literal."""
    if not isinstance(value, ast.Constant) and not isinstance(value, ast.List):
        return None
    if isinstance(value, ast.Constant):
        if value.value is None:
            return "!a field assigned None needs an annotation"
        for py, kind in ((bool, "bool"), (int, "int"), (float, "float"), (str, "str")):
            if isinstance(value.value, py):
                return kind
        return "!unsupported literal"
    return "!a field assigned a list literal needs an annotation"


def _class_fields(classdef: ast.ClassDef, scope: Any = None) -> Dict[str, Any]:
    """The kind of each instance field, from annotations and assignments in any method.

    A field is typed by an annotation, or else by the literals assigned to it. A field
    assigned something of unknown type, assigned two kinds, or named like a method is
    marked unsupported. Annotations that name a class are read in `scope`.
    """
    kinds: Dict[str, Any] = {}
    annotated: set = set()
    unknown: set = set()

    def note(name: str, kind: Any, from_annotation: bool) -> None:
        if from_annotation:
            annotated.add(name)
            kinds[name] = kind
        elif name not in annotated:
            if name in kinds and kinds[name] != kind:
                kinds[name] = f"!conflicting types for self.{name}"
            else:
                kinds.setdefault(name, kind)

    methods = {f.name for f in classdef.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for stmt in classdef.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            note(stmt.target.id, _annotation_kind(stmt.annotation, scope), True)
        elif (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
              and isinstance(stmt.targets[0], ast.Name)):
            k = _literal_kind(stmt.value)
            note(stmt.targets[0].id, k if k is not None else "!class attribute of unknown type", False)
    # Every method may assign a field, so every method is scanned: a field set to a
    # different type in another method changes what the method under analysis reads.
    for stmt in classdef.body:
        if isinstance(stmt, ast.FunctionDef):
            # A parameter with an annotation gives the type of a field assigned from it.
            param_kinds = {}
            for a in stmt.args.args:
                if a.annotation is not None:
                    try:
                        param_kinds[a.arg] = _param_kind(a, body=None, scope=scope)
                    except UnsupportedConstructError:
                        pass
            for n in ast.walk(stmt):
                target, value, annotation = None, None, None
                if isinstance(n, ast.AnnAssign):
                    target, value, annotation = n.target, n.value, n.annotation
                elif isinstance(n, ast.Assign) and len(n.targets) == 1:
                    target, value = n.targets[0], n.value
                if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                        and target.value.id == "self"):
                    continue
                if annotation is not None:
                    note(target.attr, _annotation_kind(annotation, scope), True)
                else:
                    k = _literal_kind(value)
                    if k is None and isinstance(value, ast.Name) and value.id in param_kinds:
                        k = param_kinds[value.id]
                    if k is None:
                        unknown.add(target.attr)
                    else:
                        note(target.attr, k, False)
    for name in unknown:
        if name not in annotated:
            kinds[name] = ("!field 'self.%s' is assigned a value whose type is not known here; "
                           "annotate it (self.%s: int = ...) to model it" % (name, name))
    for name in list(kinds):
        if name in methods:
            kinds[name] = f"!self.{name} is also a method or property"
    return kinds


def _method_owner(code: str, func_name: str, lineno: int) -> Optional[ast.ClassDef]:
    """The class whose body defines this method, or None for a module-level function."""
    for c in ast.walk(ast.parse(code)):
        if isinstance(c, ast.ClassDef):
            for f in c.body:
                if isinstance(f, ast.FunctionDef) and f.name == func_name and f.lineno == lineno:
                    return c
    return None


class _FieldRewriter(ast.NodeTransformer):
    """Field reads of an object become names bound to the field's symbol. A call of one
    of its methods is left for the call model, and a property read is left for it too.
    Any other use of the object is rejected: it could hand the object to code this
    model cannot see."""

    def __init__(self, env: Dict[str, Any]):
        self.env = env

    def _object(self, node: ast.expr) -> Optional[_ObjRef]:
        if isinstance(node, ast.Name) and isinstance(self.env.get(node.id), _ObjRef):
            return self.env[node.id]
        return None

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        if isinstance(node.value, ast.Name) and isinstance(self.env.get(node.value.id), _Record):
            record = self.env[node.value.id]
            if node.attr not in record.fields:
                raise UnsupportedConstructError(f"'{node.value.id}.{node.attr}' is not a field of the record")
            return ast.Name(id=f"{node.value.id}.{node.attr}", ctx=ast.Load())
        obj = self._object(node.value)
        if obj is None:
            return self.generic_visit(node)
        if node.attr in obj.overridable:
            raise UnsupportedConstructError(
                f"'{obj.label}.{node.attr}' may be overridden by a subclass, so it is not modelled")
        if node.attr in obj.properties:
            return node  # a property is a call with no arguments; see _ContainerRewriter.visit_Attribute
        if node.attr in obj.methods:
            if node.attr in obj.fields:
                obj.kind(node.attr)  # raises: a name that is both a field and a method is not modelled
            raise UnsupportedConstructError(f"method '{obj.label}.{node.attr}' used as a value is not modelled")
        name = f"{obj.prefix}{node.attr}"
        if name not in self.env:  # bound up front, unless a write has since changed it
            self.env[name] = obj.value(node.attr)
        return ast.Name(id=name, ctx=ast.Load())

    def _argument(self, node: ast.expr) -> ast.expr:
        # An object passed as an argument is handed on to the callee, not read as a value.
        return node if self._object(node) is not None else self.visit(node)

    def visit_Call(self, node: ast.Call) -> ast.expr:
        func = node.func
        obj = self._object(func.value) if isinstance(func, ast.Attribute) else None
        node.args = [self._argument(a) for a in node.args]
        node.keywords = [self.visit(k) for k in node.keywords]
        if obj is not None and func.attr in obj.methods and func.attr not in obj.properties:
            if func.attr in obj.overridable:
                raise UnsupportedConstructError(
                    f"'{obj.label}.{func.attr}' may be overridden by a subclass, so it is not modelled")
            return node  # the call itself is for the call model
        node.func = self.visit(func)
        return node

    def visit_Name(self, node: ast.Name) -> ast.expr:
        if self._object(node) is not None:
            raise UnsupportedConstructError(
                f"'{node.id}' used as a value (only reads of its fields and calls of its methods are modelled)")
        return node


def _path_of(env: Dict[str, Any]) -> Any:
    """The path condition: the branch conditions taken so far, and inside a try
    block, that no earlier operation in the block has failed."""
    base = env.get(_PATH_KEY, z3.BoolVal(True))
    cell = env.get(_TRY_KEY)
    if cell is None:
        return base
    return z3.And(base, z3.Not(z3.Or(*cell)))


# Failure kinds, and the Python exception each raises.
_FAILURE_CELL = {"index": 0, "key": 1, "type": 2, "zero": 3}


def _new_try_cell() -> List[Any]:
    return [z3.BoolVal(False) for _ in _FAILURE_CELL]


def _guard(env: Dict[str, Any], cond: Any, what: str, kind: str) -> None:
    """Require that `cond` holds wherever the code reaches here.

    Outside a try block a condition that is not proven is rejected. Inside one,
    the failure is recorded in the block's cell, and the code after it runs only
    where no failure has happened (see _path_of).
    """
    base = env.get(_PATH_KEY, z3.BoolVal(True))
    solver = z3.Solver()
    solver.set("timeout", _Z3_TIMEOUT_MS)
    solver.add(_path_of(env), z3.Not(cond))
    if solver.check() == z3.unsat:
        return
    cell = env.get(_TRY_KEY)
    if cell is None:
        raise UnsupportedConstructError(
            f"{what} may fail on some input that reaches it (not proven in range, present or not None)"
        )
    idx = _FAILURE_CELL[kind]
    cell[idx] = z3.Or(cell[idx], z3.And(base, z3.Not(cond)))


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


_ISINSTANCE_TYPES = frozenset({"int", "bool", "float", "str", "list", "dict"})


def _value_types(term: Any) -> set:
    """The Python types a translated value belongs to (bool is a subclass of int)."""
    if isinstance(term, bool) or (isinstance(term, z3.ExprRef) and term.sort() == z3.BoolSort()):
        return {"bool", "int"}
    if isinstance(term, z3.ExprRef) and term.sort() == z3.IntSort():
        return {"int"}
    if isinstance(term, z3.ExprRef) and term.sort() == z3.RealSort():
        return {"float"}
    if isinstance(term, z3.ExprRef) and term.sort() == z3.StringSort():
        return {"str"}
    return set()


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

    def _scope_class(self, name: str) -> Optional[ast.ClassDef]:
        scope = self.env.get(_SCOPE_KEY)
        return scope.class_def(name) if scope is not None else None

    # --- class and call models -------------------------------------------------

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        if isinstance(node.value, ast.Name):
            obj = self.env.get(node.value.id)
            if isinstance(obj, _ObjRef) and node.attr in obj.properties:
                return self._bind(self._inline(obj.methods[node.attr], obj, [], node))
            if node.value.id not in self.env:
                cls = self._scope_class(node.value.id)
                if cls is not None:
                    return self._bind(_class_attribute_term(cls, node.attr))
        return self.generic_visit(node)

    def _call_target(self, node: ast.Call) -> Optional[Tuple[ast.FunctionDef, Optional[_ObjRef]]]:
        """The function a call invokes, with the object it is called on, if the call model applies.

        A call to a function the scope defines, or to a method of an object (self or a
        parameter). A property is not a call target: its value is read as an attribute."""
        scope = self.env.get(_SCOPE_KEY)
        if scope is None:
            return None
        func = node.func
        if isinstance(func, ast.Name) and func.id not in self.env:
            fn = scope.function_def(func.id)
            return (fn, None) if fn is not None else None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            obj = self.env.get(func.value.id)
            if isinstance(obj, _ObjRef) and func.attr in obj.methods and func.attr not in obj.properties:
                method = obj.methods[func.attr]
                return (method, None) if _is_static(method) else (method, obj)
            if func.value.id not in self.env:
                cls = scope.class_def(func.value.id)
                method = _class_method(cls, func.attr) if cls is not None else None
                if method is not None and _is_static(method):
                    return (method, None)  # Cls.helper(...) for a staticmethod
        return None

    def _argument(self, kind: Any, node: ast.expr) -> Any:
        """The value a call passes for a parameter of this kind. Containers and objects are
        passed as themselves, so the callee sees the same object the caller does."""
        if isinstance(kind, tuple) and kind[0] == "obj":
            obj = self.env.get(node.id) if isinstance(node, ast.Name) else None
            if not isinstance(obj, _ObjRef) or obj.classdef is not kind[1]:
                raise UnsupportedConstructError("an object parameter needs an object of the same class")
            return obj
        if isinstance(kind, tuple) and kind[0] == "enum":
            value = _enum_operand(node, self.env)
            if value is None or value.classdef is not kind[1]:
                raise UnsupportedConstructError("an enum parameter needs a value of the same enum")
            return value
        if kind in ("any", "opaque"):
            return self._any_argument(node, allow_none=kind == "any")
        if isinstance(kind, tuple) and kind[0] == "list":
            if isinstance(node, ast.List):
                if kind[1] == "any":
                    raise UnsupportedConstructError("a list literal of Any values is not modelled")
                return _list_literal_value(node, self.env)
            c = self._container(node)
            if isinstance(c, _Seq) and c.opaque == (kind[1] == "any"):
                return c
            raise UnsupportedConstructError("a list parameter needs a list of the same element type")
        if isinstance(kind, tuple) and kind[0] == "dict":
            if isinstance(node, ast.Dict):
                if kind[2] == "any":
                    raise UnsupportedConstructError("a dict literal of Any values is not modelled")
                return _dict_literal_value(node, self.env)
            c = self._container(node)
            if isinstance(c, _Map) and c.opaque == (kind[2] == "any"):
                return c
            raise UnsupportedConstructError("a dict parameter needs a dict of the same value type")
        if isinstance(kind, tuple) and kind[0] == "opt":
            if isinstance(node, ast.Constant) and node.value is None:
                return _Opt(z3.BoolVal(True), _DEFAULTS[kind[1]]())
            if isinstance(node, ast.Name) and isinstance(self.env.get(node.id), _Opt):
                if isinstance(self.env[node.id].value, _AnyValue):
                    raise UnsupportedConstructError("an Any value cannot be passed for an Optional parameter of a scalar type")
                return self.env[node.id]
            term = _coerce(_as_z3_value(_expr_to_z3_safe(node, self.env)), kind[1])
            return _Opt(z3.BoolVal(False), term)
        return _coerce(_as_z3_value(_expr_to_z3_safe(node, self.env)), kind)

    def _any_argument(self, node: ast.expr, allow_none: bool = True) -> Any:
        """The value passed for an Any parameter: an Any value passed on unchanged, or None.
        A parameter of an unmodelled, non-Optional type takes no None."""
        if isinstance(node, ast.Name) and isinstance(self.env.get(node.id), _Opt) and isinstance(
                self.env[node.id].value, _AnyValue):
            return self.env[node.id]
        if allow_none and isinstance(node, ast.Constant) and node.value is None:
            return _Opt(z3.BoolVal(True), _AnyValue("None"))
        raise UnsupportedConstructError("an argument for this parameter must be an opaque value passed on unchanged")

    def _default(self, kind: Any, node: ast.expr) -> Any:
        """The value of a parameter the call leaves to its default, which must be a literal,
        or a member of the enum for an enum parameter."""
        if isinstance(kind, tuple) and kind[0] == "enum":
            value = _enum_operand(node, self.env)
            if value is None or value.classdef is not kind[1]:
                raise UnsupportedConstructError("an enum default must be a member of that enum")
            return value
        if kind in ("any", "opaque"):
            if isinstance(node, ast.Constant) and node.value is None:
                return _Opt(z3.BoolVal(True), _AnyValue("None"))
            raise UnsupportedConstructError("an opaque default is only modelled as None")
        if not isinstance(node, ast.Constant):
            raise UnsupportedConstructError("only a literal default value is modelled")
        if isinstance(kind, tuple) and kind[0] == "opt":
            if node.value is None:
                return _Opt(z3.BoolVal(True), _DEFAULTS[kind[1]]())
            return _Opt(z3.BoolVal(False), _coerce(_literal_term(node.value), kind[1]))
        if node.value is None or isinstance(kind, tuple):
            raise UnsupportedConstructError("only a literal default value is modelled")
        return _coerce(_literal_term(node.value), kind)

    def _bind_fields(self, callee: Dict[str, Any], func_node: ast.FunctionDef, name: str, obj: _ObjRef) -> None:
        """Bind the fields the callee reads through `name` to the values the caller sees now.

        A caller that wrote a field has the new value in its environment, so a call made
        after the write must read that value, not the one the object started with."""
        for attr in sorted(_attributes_on(func_node.body, name)):
            if attr in obj.methods or attr in obj.properties:
                continue
            kind = obj.fields.get(attr)
            if kind is None or (isinstance(kind, str) and kind.startswith("!")) or (
                    isinstance(kind, tuple) and kind[0] == "obj"):
                continue  # reading it raises inside the callee, which is where the reason belongs
            key = f"{obj.prefix}{attr}"
            callee[key] = self.env[key] if key in self.env else obj.value(attr)

    def _bind_params(self, name: str, params: List[Tuple[str, Any, Optional[ast.expr]]],
                     arg_nodes: List[ast.expr], keywords: List[ast.keyword]) -> Dict[str, Any]:
        """Bind a call's arguments to its parameters. `params` lists (name, kind, default)
        in order, where default is None for a parameter that must be passed. Positional
        arguments fill the parameters in order, and keywords name theirs."""
        kinds = {pname: kind for pname, kind, _ in params}
        if len(arg_nodes) > len(params):
            raise UnsupportedConstructError(f"too many arguments in a call to '{name}'")
        bound: Dict[str, Any] = {}
        for (pname, kind, _), node in zip(params, arg_nodes):
            bound[pname] = self._argument(kind, node)
        for kw in keywords:
            if kw.arg is None or kw.arg not in kinds:
                raise UnsupportedConstructError(f"a keyword argument in a call to '{name}' names no parameter")
            if kw.arg in bound:
                raise UnsupportedConstructError(f"'{kw.arg}' is passed twice in a call to '{name}'")
            bound[kw.arg] = self._argument(kinds[kw.arg], kw.value)
        for pname, kind, default in params:
            if pname in bound:
                continue
            if default is None:
                raise UnsupportedConstructError(f"a call to '{name}' does not pass '{pname}'")
            bound[pname] = self._default(kind, default)
        return bound

    def construct(self, node: ast.Call) -> _Record:
        """The record a constructor call makes: the values of the dataclass's declared fields.

        With no __init__, the declared fields are the parameters, in order, and a field
        with a default takes it. With an __init__, it runs on a fresh object, and the
        fields it sets are the record. A field it does not set takes its class default.
        The __init__ may not read a field, since a field read before it is set is not a
        value the model can give.
        """
        scope = self.env.get(_SCOPE_KEY)
        classdef = scope.class_def(node.func.id)
        _dataclass_check(classdef)
        fields = _class_fields(classdef, scope)
        declared = _declared_fields(classdef)
        for field_name, _, _ in declared:
            kind = fields.get(field_name)
            if not (kind in _SCALAR_SORTS or (isinstance(kind, tuple) and kind[0] == "enum")):
                raise UnsupportedConstructError(
                    f"field '{classdef.name}.{field_name}' is not a scalar or an enum, so the record is not modelled")
        init = _own_init(classdef)
        if init is None:
            bound = self._bind_params(classdef.name, [
                (field_name, fields[field_name], default) for field_name, _, default in declared
            ], node.args, node.keywords)
            return _Record(classdef, bound)

        args = init.args
        if args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs or not args.args:
            raise UnsupportedConstructError(f"the __init__ of '{classdef.name}' has parameters that are not modelled")
        self_name = args.args[0].arg
        if any(isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load)
               and isinstance(n.value, ast.Name) and n.value.id == self_name
               for n in ast.walk(ast.Module(body=list(init.body), type_ignores=[]))):
            raise UnsupportedConstructError(f"the __init__ of '{classdef.name}' reads a field before setting it")
        defaults = dict(zip((p.arg for p in args.args[len(args.args) - len(args.defaults):]), args.defaults))
        bound = self._bind_params(classdef.name, [
            (p.arg, _param_kind(p, init.body, scope), defaults.get(p.arg)) for p in args.args[1:]
        ], node.args, node.keywords)

        callee: Dict[str, Any] = {
            _PATH_KEY: _path_of(self.env),
            _FACTS_KEY: self.env.setdefault(_FACTS_KEY, []),
            _SCOPE_KEY: scope,
            _CALL_STACK_KEY: self.env.get(_CALL_STACK_KEY, ()) + (f"{classdef.name}.__init__",),
            _MAX_UNROLL_KEY: self.env.get(_MAX_UNROLL_KEY, DEFAULT_MAX_UNROLL),
            self_name: _ObjRef(fields, {}, self.env.setdefault(_FACTS_KEY, []),
                               classdef=classdef, scope=scope, is_self=True),
        }
        callee.update(bound)
        flow = _exec_stmts(list(init.body), callee, callee[_MAX_UNROLL_KEY])
        if flow[0] != "fallthrough":
            raise UnsupportedConstructError(f"the __init__ of '{classdef.name}' returns or raises")
        values: Dict[str, Any] = {}
        for field_name, _, default in declared:
            key = f"self__{field_name}"
            if key in flow[1]:
                values[field_name] = flow[1][key]
            elif default is not None:
                values[field_name] = self._default(fields[field_name], default)
            else:
                raise UnsupportedConstructError(
                    f"the __init__ of '{classdef.name}' does not set '{field_name}'")
        return _Record(classdef, values)

    def _inline(self, func_node: ast.FunctionDef, obj: Optional[_ObjRef], arg_nodes: List[ast.expr],
                call_node: ast.AST) -> Any:
        """The value of a call, from executing the callee's body with its arguments bound.

        The callee sees only its parameters, its own locals and the fields of the objects
        it is given, at the values the caller sees. It cannot see the caller's locals, so
        a name it does not bind is still rejected. A call that writes a field, recurses,
        raises or does not return on every path is not modelled.
        """
        name = func_node.name
        stack = self.env.get(_CALL_STACK_KEY, ())
        if name in stack or len(stack) >= MAX_CALL_DEPTH:
            raise UnsupportedConstructError(f"recursive or deeply nested call to '{name}' is not modelled")
        decorators = {_base_name(d) for d in func_node.decorator_list}
        if "classmethod" in decorators:
            raise UnsupportedConstructError(f"'{name}' is a class method, which is not modelled")
        if decorators - {"property", "staticmethod"}:
            # Any other decorator may replace the body, so the body is not what runs.
            raise UnsupportedConstructError(f"'{name}' is decorated, and a decorator is not modelled")
        if "staticmethod" in decorators and obj is not None:
            raise UnsupportedConstructError(f"'{name}' is a static method, called on an object, which is not modelled")
        args = func_node.args
        if args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs:
            raise UnsupportedConstructError(f"'{name}' has variable or keyword-only parameters, which are not modelled")
        if any(_writes_fields(func_node, a.arg) for a in args.args):
            raise UnsupportedConstructError(f"'{name}' writes a field, which a call does not model")

        params = args.args
        if obj is not None and not params:
            raise UnsupportedConstructError(f"method '{name}' has no self parameter")
        bound: Dict[str, Any] = {params[0].arg: obj} if obj is not None else {}
        callee_params = params[1:] if obj is not None else params
        scope = self.env.get(_SCOPE_KEY)
        defaults = dict(zip((p.arg for p in params[len(params) - len(args.defaults):]), args.defaults))
        bound.update(self._bind_params(name, [
            (p.arg, _param_kind(p, func_node.body, scope), defaults.get(p.arg)) for p in callee_params
        ], arg_nodes, list(getattr(call_node, "keywords", []))))

        callee: Dict[str, Any] = {
            _PATH_KEY: _path_of(self.env),  # the call runs only where the caller reaches it
            _FACTS_KEY: self.env.setdefault(_FACTS_KEY, []),  # domain restrictions are the caller's
            _SCOPE_KEY: scope,
            _CALL_STACK_KEY: stack + (name,),
            _MAX_UNROLL_KEY: self.env.get(_MAX_UNROLL_KEY, DEFAULT_MAX_UNROLL),
        }
        callee.update(bound)
        for pname, value in bound.items():
            if isinstance(value, _ObjRef):
                self._bind_fields(callee, func_node, pname, value)
        flow = _exec_stmts(list(func_node.body), callee, callee[_MAX_UNROLL_KEY])
        if flow[0] != "return":
            raise UnsupportedConstructError(
                f"a call to '{name}' may raise or fall off its end, so its value is not modelled")
        if isinstance(flow[1], _Record):
            raise UnsupportedConstructError(f"a call to '{name}' returns an object, which only a return can give")
        return _as_z3_value(flow[1])

    def visit_Name(self, node: ast.Name) -> ast.expr:
        if isinstance(self.env.get(node.id), _Record):
            raise UnsupportedConstructError(
                f"'{node.id}' is an object built by a constructor, used as a value only as a whole return")
        if node.id.startswith(_TEMP_PREFIX) and not getattr(node, "is_temp", False):
            raise UnsupportedConstructError(f"name '{node.id}' is reserved")
        if isinstance(self.env.get(node.id), _Unbound):
            raise UnsupportedConstructError(
                f"'{node.id}' may be unbound here (it is the target of a loop over a container)")
        if isinstance(self.env.get(node.id), _Opaque):
            raise UnsupportedConstructError(f"'{node.id}' is an imported name, which is not modelled")
        if isinstance(self.env.get(node.id), _Enum):
            raise UnsupportedConstructError(
                f"'{node.id}' is an enum value, which is only modelled in comparisons with a member")
        if node.id not in self.env and self._scope_class(node.id) is not None:
            raise UnsupportedConstructError(f"class '{node.id}' used as a value is not modelled")
        scope = self.env.get(_SCOPE_KEY)
        if node.id not in self.env and scope is not None and scope.is_module_flag(node.id):
            # A module flag set to True or False by the module: its value is unknown, and the
            # same in every use, so it is one Boolean.
            self.env[node.id] = z3.Bool(node.id)
        if (node.id not in self.env and node.id not in _MODELLED_BUILTINS
                and not self.env.get(_EXPRESSION_KEY)):
            # A free name would be read as an unknown integer, but it is a global or a
            # builtin whose value and type this model does not know.
            raise UnsupportedConstructError(
                f"'{node.id}' is neither a parameter nor a local, so it is a global or builtin, "
                "which is not modelled")
        if isinstance(self.env.get(node.id), _Opt):
            opt = self.env[node.id]
            if isinstance(opt.value, _AnyValue):
                raise UnsupportedConstructError(
                    f"'{node.id}' is an Any value, which is only modelled in a None test or passed on unchanged")
            _guard(self.env, z3.Not(opt.isnone), f"value of '{node.id}' (may be None)", "type")
            return self._bind(opt.value)
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
        if c.opaque:
            raise UnsupportedConstructError(
                f"an element of '{node.value.id}', a container of Any values, is not modelled")
        index = _expr_to_z3_safe(self.visit(node.slice), self.env)
        if isinstance(c, _Seq):
            i = _as_key_term(index, z3.IntSort())
            _guard(self.env, z3.And(-c.length <= i, i < c.length),
                   f"index into '{node.value.id}'", "index")
            pos = z3.If(i < 0, i + c.length, i)  # Python's negative indexing
            return self._bind(z3.Select(c.items, pos))
        k = _as_key_term(index, c.present.domain())
        _guard(self.env, z3.Select(c.present, k), f"key into '{node.value.id}'", "key")
        return self._bind(z3.Select(c.values, k))

    def _under(self, cond: Any, node: ast.expr) -> Any:
        """Translate `node` on the path where `cond` holds, then restore the path."""
        saved = _path_of(self.env)
        self.env[_PATH_KEY] = z3.And(saved, cond)
        try:
            return _expr_to_z3_safe(self.visit(node), self.env)
        finally:
            self.env[_PATH_KEY] = saved

    def _opaque_isinstance(self, value: "_Opt", types: List[ast.expr]) -> Any:
        """isinstance of an opaque value. Its type is fixed, but not known, so each test is one
        Boolean named for the value and the type: repeated tests of the same type agree. None is
        an instance of no type but object."""
        self.env.setdefault(_FACTS_KEY, []).append(_TYPE_TEST_NOTE)
        terms = []
        for t in types:
            label = t.id if isinstance(t, ast.Name) else ast.unparse(t) if isinstance(t, ast.Attribute) else None
            if label is None:
                raise UnsupportedConstructError("isinstance needs a class name")
            if label == "object":
                terms.append(z3.BoolVal(True))  # every value, None included, is an object
                continue
            test = z3.Bool(f"isinstance[{value.value.name}, {label}]")
            terms.append(z3.If(value.isnone, z3.BoolVal(False), test))
        return z3.Or(*terms)

    def _isinstance(self, node: ast.Call) -> Any:
        """isinstance(x, T) as a Z3 term. For an opaque value, see _opaque_isinstance. Otherwise
        it is decided from the value's sort: parameters are taken to have the types their
        annotations state, which is recorded as a domain note."""
        types = node.args[1].elts if isinstance(node.args[1], ast.Tuple) else [node.args[1]]
        arg = node.args[0]
        if isinstance(arg, ast.Name) and isinstance(self.env.get(arg.id), _Opt) and isinstance(
                self.env[arg.id].value, _AnyValue):
            return self._opaque_isinstance(self.env[arg.id], types)
        return z3.BoolVal(self._isinstance_of_sort(node, types))

    def _isinstance_of_sort(self, node: ast.Call, types: List[ast.expr]) -> bool:
        self.env.setdefault(_FACTS_KEY, []).append(_TYPE_NOTE)
        names = {t.id for t in types if isinstance(t, ast.Name)}
        if len(names) != len(types) or not names <= _ISINSTANCE_TYPES:
            raise UnsupportedConstructError("isinstance is only modelled for int, bool, float, str, list and dict")
        value = self.visit(node.args[0])
        if isinstance(value, ast.Name) and isinstance(self.env.get(value.id), _Opt):
            raise UnsupportedConstructError("isinstance of an Optional parameter is not modelled")
        term = _as_z3_value(_expr_to_z3_safe(value, self.env))
        kinds = _value_types(term)
        return bool(kinds & names)

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

    def _none_test(self, node: ast.Compare) -> ast.expr:
        """`x is None` / `x is not None` / `==` / `!=` for a parameter name."""
        if not isinstance(node.left, ast.Name) or node.left.id not in self.env:
            raise UnsupportedConstructError("None can only be compared with a parameter or name")
        value = self.env[node.left.id]
        is_none = isinstance(node.ops[0], (ast.Is, ast.Eq))
        if isinstance(value, _Opt):
            test = value.isnone
        elif isinstance(value, (_Seq, _Map, _Unbound)):
            raise UnsupportedConstructError(f"None comparison of '{node.left.id}' is not modelled")
        else:
            test = z3.BoolVal(False)  # a value that is never None
        return self._bind(test if is_none else z3.Not(test))

    def visit_Call(self, node: ast.Call) -> ast.expr:
        if (isinstance(node.func, ast.Name) and node.func.id == "isinstance" and len(node.args) == 2):
            return self._bind(self._isinstance(node))
        if (isinstance(node.func, ast.Name) and node.func.id == "len" and len(node.args) == 1
                and isinstance(node.args[0], ast.Name)):
            c = self._container(node.args[0])
            if isinstance(c, _Seq):
                return self._bind(c.length)
            if isinstance(c, _Map):
                raise UnsupportedConstructError("len() of a dict is not modelled")
        if _is_constructor_call(node, self.env):
            raise UnsupportedConstructError(
                "a constructor call is modelled only as a whole return or an assigned value")
        target = self._call_target(node)
        if target is not None:
            func_node, obj = target
            return self._bind(self._inline(func_node, obj, node.args, node))
        return self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> ast.expr:
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            divisor = _as_z3_value(_expr_to_z3_safe(self.visit(node.right), self.env))
            _guard(self.env, divisor != 0, "division by a value that may be zero", "zero")
            if isinstance(node.op, ast.Div):
                # Real division, now proven non-zero: computed here, since the shared
                # translator refuses a divisor that is not a literal.
                left = _as_z3_value(_expr_to_z3_safe(self.visit(node.left), self.env))
                return self._bind(_as_real(left) / _as_real(divisor))
            if not isinstance(node.right, ast.Constant):
                # A literal divisor stays a literal, which the // and % rule needs to see.
                node = ast.BinOp(left=node.left, op=node.op, right=self._bind(divisor))
        return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> ast.expr:
        if len(node.ops) == 1 and isinstance(node.ops[0], (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)):
            left = _enum_operand(node.left, self.env)
            right = _enum_operand(node.comparators[0], self.env)
            if left is not None or right is not None:
                # Members are compared by identity: two members of one enum are equal only
                # if they are the same member, and members of different enums never are.
                if left is None or right is None:
                    raise UnsupportedConstructError("an enum value is only modelled as compared with an enum value")
                same = left.classdef is right.classdef
                equal = (left.term == right.term) if same else z3.BoolVal(False)
                return self._bind(equal if isinstance(node.ops[0], (ast.Is, ast.Eq)) else z3.Not(equal))
        if (len(node.ops) == 1 and isinstance(node.ops[0], (ast.In, ast.NotIn))
                and isinstance(node.comparators[0], ast.List)):
            # `x in [a, b]` is `x == a or x == b`, for scalar elements
            left = _as_z3_value(_expr_to_z3_safe(self.visit(node.left), self.env))
            options = [z3.BoolVal(False)] + [
                left == _as_z3_value(_expr_to_z3_safe(self.visit(e), self.env))
                for e in node.comparators[0].elts]
            found = z3.Or(*options)
            return self._bind(found if isinstance(node.ops[0], ast.In) else z3.Not(found))
        if (len(node.ops) == 1 and isinstance(node.ops[0], (ast.Is, ast.IsNot, ast.Eq, ast.NotEq))
                and isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value is None):
            return self._none_test(node)
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


_SCALAR_SORTS = {"int": z3.IntSort, "bool": z3.BoolSort, "str": z3.StringSort, "float": z3.RealSort}


def _literal_term(value: Any) -> Any:
    """A Python literal from a default value or a class attribute, as a Z3 term."""
    if isinstance(value, bool):
        return z3.BoolVal(value)
    if isinstance(value, int):
        return z3.IntVal(value)
    if isinstance(value, float):
        return z3.RealVal(value)
    if isinstance(value, str):
        return z3.StringVal(value)
    raise UnsupportedConstructError(f"literal {value!r} is not modelled")


def _coerce(term: Any, kind: Any) -> Any:
    """A value passed for a parameter of scalar kind: an int may widen to a float, and any
    other sort mismatch is rejected, since Python would pass the value unchanged."""
    if kind == "unused":
        return term
    if kind == "float" and term.sort() == z3.IntSort():
        return z3.ToReal(term)
    if term.sort() != _SCALAR_SORTS[kind]():
        raise UnsupportedConstructError(
            f"a value of sort {term.sort()} is passed for a parameter of type {kind}")
    return term


def _enum_operand(node: ast.expr, env: Dict[str, Any]) -> Optional[_Enum]:
    """The enum value an operand denotes: a name bound to one, a member of an enum class
    the scope defines, or a conditional between two enum values. None for any other operand."""
    if isinstance(node, ast.Name) and isinstance(env.get(node.id), _Enum):
        return env[node.id]
    if isinstance(node, ast.IfExp):
        cond = _expr_to_z3_safe(node.test, env)
        if not isinstance(cond, z3.BoolRef):
            raise UnsupportedConstructError("a conditional expression's test must be a boolean")
        then_value, else_value = _enum_operand(node.body, env), _enum_operand(node.orelse, env)
        if then_value is None or else_value is None or then_value.classdef is not else_value.classdef:
            raise UnsupportedConstructError("a conditional between enum values needs two members of one enum")
        return _Enum(then_value.classdef, z3.If(cond, then_value.term, else_value.term))
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id not in env:
        scope = env.get(_SCOPE_KEY)
        cls = scope.class_def(node.value.id) if scope is not None else None
        members = _enum_members(cls) if cls is not None else None
        if members is not None:
            if node.attr not in members:
                raise UnsupportedConstructError(f"'{node.value.id}.{node.attr}' is not a member of the enum")
            return _Enum(cls, z3.IntVal(members[node.attr]))
    return None


def _class_attribute_term(cls: ast.ClassDef, attr: str) -> Any:
    """The value of `Cls.attr` when the class assigns it a literal. An enum member is a
    value of the enum, which only a comparison can use."""
    if (_enum_members(cls) or {}).get(attr) is not None:
        raise UnsupportedConstructError(
            f"enum member '{cls.name}.{attr}' is only modelled in a comparison with an enum value")
    assigns = [s for s in cls.body if isinstance(s, ast.Assign) and len(s.targets) == 1
               and isinstance(s.targets[0], ast.Name) and s.targets[0].id == attr]
    if len(assigns) == 1 and isinstance(assigns[0].value, ast.Constant) and assigns[0].value.value is not None:
        return _literal_term(assigns[0].value.value)
    raise UnsupportedConstructError(f"class attribute '{cls.name}.{attr}' is not a literal, so it is not modelled")


def _is_static(func: ast.FunctionDef) -> bool:
    return any(_name_of(d) == "staticmethod" for d in func.decorator_list)


def _class_method(classdef: ast.ClassDef, name: str) -> Optional[ast.FunctionDef]:
    """The method a class defines once under `name`, or None."""
    defs = [s for s in classdef.body if isinstance(s, ast.FunctionDef) and s.name == name]
    return defs[0] if len(defs) == 1 else None


def _dataclass_check(classdef: ast.ClassDef) -> None:
    """Raise unless the class is a dataclass whose `==` is the comparison of its fields.

    A plain class compares by identity, and `eq=False` makes a dataclass do so too, so
    neither is modelled. A base class, or a __post_init__, could add to or change the
    fields, and a class's own __eq__ replaces the comparison, so none is modelled either."""
    decorators = [d for d in classdef.decorator_list if _name_of(d.func if isinstance(d, ast.Call) else d) == "dataclass"]
    if not decorators:
        raise UnsupportedConstructError(
            f"class '{classdef.name}' is not a dataclass, and only a dataclass is compared by its fields")
    for d in decorators:
        if isinstance(d, ast.Call) and any(k.arg == "eq" and not (isinstance(k.value, ast.Constant) and k.value.value)
                                           for k in d.keywords):
            raise UnsupportedConstructError(f"dataclass '{classdef.name}' is not compared by its fields (eq=False)")
    if classdef.bases:
        raise UnsupportedConstructError(f"dataclass '{classdef.name}' has a base class, which is not modelled")
    if any(isinstance(s, ast.FunctionDef) and s.name == "__post_init__" for s in classdef.body):
        raise UnsupportedConstructError(f"dataclass '{classdef.name}' has __post_init__, which is not modelled")
    if any(isinstance(s, ast.FunctionDef) and s.name == "__eq__" for s in classdef.body):
        raise UnsupportedConstructError(f"dataclass '{classdef.name}' defines __eq__, so it is not compared by its fields")


def _declared_fields(classdef: ast.ClassDef) -> List[Tuple[str, ast.expr, Optional[ast.expr]]]:
    """The fields a dataclass declares, in order: (name, annotation, default or None).
    A default made by field(default=...) is its value. A factory default is not modelled."""
    out = []
    for stmt in classdef.body:
        if not (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)):
            continue
        if _name_of(stmt.annotation) == "ClassVar":
            continue
        default = stmt.value
        if isinstance(default, ast.Call) and _name_of(default.func) == "field":
            options = {k.arg: k.value for k in default.keywords}
            if default.args or set(options) - {"default"}:
                raise UnsupportedConstructError(
                    f"field '{stmt.target.id}' uses field() options that are not modelled")
            default = options.get("default")
        out.append((stmt.target.id, stmt.annotation, default))
    return out


def _own_init(classdef: ast.ClassDef) -> Optional[ast.FunctionDef]:
    inits = [s for s in classdef.body if isinstance(s, ast.FunctionDef) and s.name == "__init__"]
    if len(inits) > 1 or (inits and inits[0].decorator_list):
        raise UnsupportedConstructError(f"class '{classdef.name}' has an __init__ that is not modelled")
    return inits[0] if inits else None


def _is_constructor_call(node: ast.expr, env: Dict[str, Any]) -> bool:
    scope = env.get(_SCOPE_KEY)
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id not in env
            and scope is not None and scope.class_def(node.func.id) is not None)


def _record_of(node: ast.expr, env: Dict[str, Any]) -> Optional[_Record]:
    """The record a value is, when it is a constructor call or a name bound to a record."""
    if isinstance(node, ast.Name) and isinstance(env.get(node.id), _Record):
        return env[node.id]
    if _is_constructor_call(node, env):
        return _ContainerRewriter(env).construct(node)
    return None


def _bind_record(env: Dict[str, Any], name: str, record: _Record) -> None:
    """Bind a name to a record, and each of its fields as `name.field`, which reads use."""
    env[name] = record
    for field_name, term in record.fields.items():
        env[f"{name}.{field_name}"] = term


def _select(cond: Any, a: Any, b: Any) -> Any:
    """`a` where cond holds and `b` elsewhere: a Z3 term, or a record if both are records."""
    if isinstance(a, _Record) and isinstance(b, _Record):
        if a.classdef is not b.classdef:
            raise UnsupportedConstructError("the two branches return objects of different classes")
        return _Record(a.classdef, {f: _field_select(cond, a.fields[f], b.fields[f]) for f in a.fields})
    return z3.If(cond, _as_z3_value(a), _as_z3_value(b))


def _field_equal(x: Any, y: Any) -> Any:
    """Equality of two field values: enum members by identity, and terms by value."""
    if isinstance(x, _Enum) or isinstance(y, _Enum):
        if not (isinstance(x, _Enum) and isinstance(y, _Enum)) or x.classdef is not y.classdef:
            return z3.BoolVal(False)  # members of different enums, or an enum and a number, are never equal
        return x.term == y.term
    return x == y


def _field_select(cond: Any, x: Any, y: Any) -> Any:
    if isinstance(x, _Enum) or isinstance(y, _Enum):
        if not (isinstance(x, _Enum) and isinstance(y, _Enum) and x.classdef is y.classdef):
            raise UnsupportedConstructError("a field takes an enum value on one branch and another value on the other")
        return _Enum(x.classdef, z3.If(cond, x.term, y.term))
    return z3.If(cond, x, y)


def _same_result(a: Any, b: Any) -> Any:
    """The condition under which two results are equal. Records are equal when every field is."""
    if isinstance(a, _Record) or isinstance(b, _Record):
        if not (isinstance(a, _Record) and isinstance(b, _Record)) or a.classdef is not b.classdef:
            raise UnsupportedConstructError("the two functions return objects of different classes, or an object on one side only")
        return z3.And(*[_field_equal(a.fields[f], b.fields[f]) for f in a.fields]) if a.fields else z3.BoolVal(True)
    return _as_z3_value(a) == _as_z3_value(b)


_DEFAULT_OF_SORT = {z3.RealSort(): z3.RealVal(0), z3.IntSort(): z3.IntVal(0),
                    z3.StringSort(): z3.StringVal(""), z3.BoolSort(): z3.BoolVal(False)}


def _dict_literal_value(node: ast.Dict, env: Dict[str, Any]) -> _Map:
    """A dict literal with int or str keys and scalar values, each of one sort.

    As in Python, the pairs are evaluated in order, and a repeated key keeps its last
    value. An empty literal has no key sort, so a key of the wrong sort used on it is
    rejected when it is used (see _as_key_term).
    """
    if any(k is None for k in node.keys):
        raise UnsupportedConstructError("a dict literal with ** unpacking is not modelled")
    pairs = [(_as_z3_value(_expr_to_z3_safe(k, env)), _as_z3_value(_expr_to_z3_safe(v, env)))
             for k, v in zip(node.keys, node.values)]
    if not pairs:
        return _Map(z3.K(z3.IntSort(), z3.BoolVal(False)), z3.K(z3.IntSort(), z3.IntVal(0)))
    key_sort, value_sort = pairs[0][0].sort(), pairs[0][1].sort()
    if key_sort not in (z3.IntSort(), z3.StringSort()):
        raise UnsupportedConstructError("dict literal keys must be int or str")
    if value_sort not in _DEFAULT_OF_SORT:
        raise UnsupportedConstructError("dict literal values must be int, float, str or bool")
    present = z3.K(key_sort, z3.BoolVal(False))
    values = z3.K(key_sort, _DEFAULT_OF_SORT[value_sort])
    for key, value in pairs:
        if key.sort() != key_sort or value.sort() != value_sort:
            raise UnsupportedConstructError("dict literal keys and values must each share one sort")
        present = z3.Store(present, key, z3.BoolVal(True))
        values = z3.Store(values, key, value)
    return _Map(present, values)


def _list_literal_value(node: ast.List, env: Dict[str, Any]) -> _Seq:
    values = [_as_z3_value(_expr_to_z3_safe(elt, env)) for elt in node.elts]
    if not values:
        # No element is ever read: every read is guarded by a length test that is false.
        return _Seq(z3.IntVal(0), z3.K(z3.IntSort(), z3.IntVal(0)))
    sort = values[0].sort()
    if sort not in (z3.IntSort(), z3.RealSort(), z3.StringSort(), z3.BoolSort()):
        raise UnsupportedConstructError("list literal elements must be int, float, str or bool")
    default = {z3.RealSort(): z3.RealVal(0), z3.IntSort(): z3.IntVal(0), z3.StringSort(): z3.StringVal(""),
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
    domain: Optional[str] = None   # set when a loop over a container bounds the lengths checked

    def summary(self) -> str:
        if self.status == "unsupported":
            return f"Cannot determine — unsupported construct: {self.reason}"
        if self.status == "unknown":
            return f"Cannot determine — Z3 timed out: {self.reason}"
        scope = f" ({self.domain})" if self.domain else ""
        if self.equivalent:
            return f"PROVEN EQUIVALENT for all inputs in the supported domain{scope}."
        return f"NOT EQUIVALENT — counterexample: {self.counterexample}{scope}"


@dataclass
class SimplificationResult:
    """Result of simplify_function()."""
    status: str  # "simplified" | "already_simplest" | "unsupported"
    original_expr: Optional[str] = None
    simplified_expr: Optional[str] = None  # Z3 string form
    reason: Optional[str] = None
    simplified_python: Optional[str] = None  # runnable Python expression over the same parameter names
    domain: Optional[str] = None  # set when a loop over a container bounds the lengths checked

    def summary(self) -> str:
        if self.status == "unsupported":
            return f"Cannot simplify — unsupported construct: {self.reason}"
        scope = f" [{self.domain}]" if self.domain else ""
        if self.status == "already_simplest":
            return f"No algebraic simplification found: {self.original_expr}{scope}"
        if self.simplified_python is not None:
            return f"{self.original_expr}  =>  {self.simplified_python}{scope}"
        return f"{self.original_expr}  =>  {self.simplified_expr}{scope}"


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

def _branch_flows(cond, then_flow, then_env, else_flow, else_env, env, rest, max_unroll):
    """Combine the flows of the two sides of a conditional on `cond`.

    `rest` is the code that follows the conditional. It runs on whichever side
    falls through, and its own flow is part of the result. A side that raises is
    excluded from the domain, so the other side's flow stands for every input.
    """
    if then_flow[0] == "raised" and else_flow[0] == "raised":
        return ("raised", None)
    if then_flow[0] == "raised":
        return else_flow if else_flow[0] == "return" else _exec_stmts(rest, else_env, max_unroll)
    if else_flow[0] == "raised":
        return then_flow if then_flow[0] == "return" else _exec_stmts(rest, then_env, max_unroll)
    if then_flow[0] == "return" and else_flow[0] == "return":
        return ("return", _select(cond, then_flow[1], else_flow[1]))

    if then_flow[0] == "fallthrough" and else_flow[0] == "fallthrough":
        env.update(_merge_envs(cond, then_env, else_env, env))
        return _exec_stmts(rest, env, max_unroll)

    # Exactly one branch returns and the other falls through: this
    # is the ordinary "early return" pattern (`if cond: return X` /
    # then more code, or the mirror image). The branch that falls
    # through continues into the REMAINING statements (using its
    # own env), and that remainder must itself resolve to a
    # definite return for the combination to be well-defined -
    # otherwise the function genuinely doesn't return on every
    # path, which is correctly rejected rather than guessed at.
    if then_flow[0] == "return" and else_flow[0] == "fallthrough":
        remainder = _exec_stmts(rest, else_env, max_unroll)
        if remainder[0] == "raised":
            return ("return", then_flow[1])
        if remainder[0] != "return":
            raise UnsupportedConstructError(
                "function does not return a value on every path"
            )
        return ("return", _select(cond, then_flow[1], remainder[1]))

    if then_flow[0] == "fallthrough" and else_flow[0] == "return":
        remainder = _exec_stmts(rest, then_env, max_unroll)
        if remainder[0] == "raised":
            return ("return", else_flow[1])
        if remainder[0] != "return":
            raise UnsupportedConstructError(
                "function does not return a value on every path"
            )
        return ("return", _select(cond, remainder[1], else_flow[1]))

    raise UnsupportedConstructError("unreachable if/else flow combination")




_EXCEPTION_KINDS = {
    "IndexError": {"index"},
    "KeyError": {"key"},
    "LookupError": {"index", "key"},
    "TypeError": {"type"},
    "ZeroDivisionError": {"zero"},
    "ArithmeticError": {"zero"},
    "Exception": {"index", "key", "type", "zero"},
}


def _assigned_names(stmts: List[ast.stmt]) -> set:
    return {n.id for n in ast.walk(ast.Module(body=list(stmts), type_ignores=[]))
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}


def _exec_try(stmt: ast.Try, env: Dict[str, Any], rest: List[ast.stmt], max_unroll: int):
    """try/except around the failures this model can detect (index, key, None).

    Each failing operation in the body is recorded in a cell instead of rejected.
    The body's later statements run only where nothing has failed. The handler
    runs where a caught failure happened. A failure the handler does not catch
    is excluded from the verified domain, and the domain note says so.
    """
    if stmt.orelse or stmt.finalbody or len(stmt.handlers) != 1:
        raise UnsupportedConstructError("only one except clause, with no else or finally, is modelled")
    handler = stmt.handlers[0]
    if env.get(_TRY_KEY) is not None:
        raise UnsupportedConstructError("nested try blocks are not modelled")
    unmodelled = None
    if handler.type is None:
        caught = {"index", "key", "type", "zero"}
    else:
        caught = set()
        for t in (handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]):
            if isinstance(t, ast.Name) and t.id in _EXCEPTION_KINDS:
                caught |= _EXCEPTION_KINDS[t.id]
            else:
                unmodelled = unmodelled or ast.unparse(t)
    if unmodelled is None and handler.name is not None:
        raise UnsupportedConstructError("'except ... as name' is not modelled")
    # The handler sees the variables as they were before the try. A variable the
    # body reassigns would show its value from partway through the body, so reject.
    handler_reads = {n.id for n in ast.walk(ast.Module(body=list(handler.body), type_ignores=[]))
                     if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    if _assigned_names(stmt.body) & handler_reads:
        raise UnsupportedConstructError("the handler reads a variable that the try body assigns")

    base = _path_of(env)
    cell = _new_try_cell()
    body_env = dict(env)
    body_env[_TRY_KEY] = cell
    body_flow = _exec_stmts(list(stmt.body), body_env, max_unroll)

    if unmodelled is not None:
        # Only a handler that can never run may name an exception this model does not know.
        if not z3.is_false(z3.simplify(z3.Or(*cell))):
            raise UnsupportedConstructError(f"except {unmodelled} is not modelled")
        normal_env = {k: v for k, v in body_env.items() if k != _TRY_KEY}
        normal_env[_PATH_KEY] = base
        return _branch_flows(z3.BoolVal(False), ("raised", None), env, body_flow, normal_env,
                             env, rest, max_unroll)

    facts = env.setdefault(_FACTS_KEY, [])
    for kind, idx in _FAILURE_CELL.items():
        if kind in caught or z3.is_false(z3.simplify(cell[idx])):
            continue  # either handled, or this program cannot fail that way
        facts.append(z3.Not(cell[idx]))
        facts.append(_TRY_NOTE)  # _notes_of keeps one copy
    matched = z3.Or(*[cell[_FAILURE_CELL[k]] for k in caught])

    handler_env = dict(env)
    handler_env.pop(_TRY_KEY, None)
    handler_env[_PATH_KEY] = z3.And(base, matched)
    handler_flow = _exec_stmts(list(handler.body), handler_env, max_unroll)

    normal_env = {k: v for k, v in body_env.items() if k != _TRY_KEY}
    normal_env[_PATH_KEY] = z3.And(base, z3.Not(z3.Or(*cell)))
    return _branch_flows(matched, handler_flow, handler_env, body_flow, normal_env, env, rest, max_unroll)


def _is_self_field_write(stmt: ast.Assign, env: Dict[str, Any]) -> bool:
    if len(stmt.targets) != 1:
        return False
    t = stmt.targets[0]
    targets = t.elts if isinstance(t, ast.Tuple) else [t]
    return bool(targets) and all(
        isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)
        and isinstance(env.get(x.value.id), _ObjRef) and env[x.value.id].is_self for x in targets)


def _field_value(kind: Any, node: ast.expr, env: Dict[str, Any]) -> Any:
    """The value assigned to a field of this kind: an enum member, or a Z3 term."""
    if isinstance(kind, tuple) and kind[0] == "enum":
        value = _enum_operand(node, env)
        if value is None:
            raise UnsupportedConstructError("an enum field is assigned a member of its enum, or nothing modelled")
        return value
    return _expr_to_z3_safe(node, env)


def _write_self_fields(stmt: ast.Assign, env: Dict[str, Any]) -> None:
    """self.f = e, and self.f, self.g = e1, e2, for scalar fields. From here on the
    field has the new value in this environment, and the return and the final state see it."""
    t = stmt.targets[0]
    targets = list(t.elts) if isinstance(t, ast.Tuple) else [t]
    if isinstance(t, ast.Tuple):
        if not (isinstance(stmt.value, ast.Tuple) and len(stmt.value.elts) == len(targets)):
            raise UnsupportedConstructError("tuple assignment to fields needs a tuple of the same length")
        exprs = list(stmt.value.elts)
    else:
        exprs = [stmt.value]
    # every right-hand side is evaluated before any write
    values = [_field_value(env[t.value.id].kind(t.attr), e, env) for t, e in zip(targets, exprs)]
    for target, value in zip(targets, values):
        kind = env[target.value.id].kind(target.attr)
        if isinstance(kind, tuple) and kind[0] == "enum":
            if not isinstance(value, _Enum) or value.classdef is not kind[1]:
                raise UnsupportedConstructError(f"'self.{target.attr}' is an enum but is assigned another value")
            env[f"self__{target.attr}"] = value
            continue
        if kind not in _SCALAR_FIELD_KINDS:
            raise UnsupportedConstructError(
                f"writes to 'self.{target.attr}' ({kind}) are not modelled: only scalar fields are written")
        term = _as_z3_value(value)
        if kind == "float" and term.sort() == z3.IntSort():
            term = z3.ToReal(term)
        if term.sort() != _SORTS[kind]():
            raise UnsupportedConstructError(
                f"'self.{target.attr}' is {kind} but is assigned a value of another type")
        env[f"self__{target.attr}"] = term


def _exec_stmts(
    stmts: List[ast.stmt],
    env: Dict[str, Any],
    max_unroll: int,
) -> Tuple[str, Any]:
    for idx, stmt in enumerate(stmts):
        if isinstance(stmt, ast.Return):
            if stmt.value is None:
                raise UnsupportedConstructError("bare 'return' (no value)")
            record = _record_of(stmt.value, env)
            value = record if record is not None else _expr_to_z3_safe(stmt.value, env)
            exits = env.get(_EXITS_KEY)
            if exits is not None:
                state = {k: v for k, v in env.items() if k.startswith("self__") and isinstance(v, z3.ExprRef)}
                exits.append((_path_of(env), state))
            return ("return", value)

        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is None:
                continue  # a bare annotation binds nothing
            if not isinstance(stmt.target, ast.Name):
                raise UnsupportedConstructError(
                    "annotated assignment target must be a simple name"
                )
            record = _record_of(stmt.value, env)
            if record is not None:
                _bind_record(env, stmt.target.id, record)
                continue
            if isinstance(stmt.value, ast.List):
                env[stmt.target.id] = _list_literal_value(stmt.value, env)  # `xs: List[int] = [...]`
                continue
            if isinstance(stmt.value, ast.Dict):
                env[stmt.target.id] = _dict_literal_value(stmt.value, env)  # `d: Dict[str, int] = {...}`
                continue
            env[stmt.target.id] = _expr_to_z3_safe(stmt.value, env)
            continue

        if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Attribute) and _self_ref_in(env):
            # self.f op= e  is  self.f = self.f op e
            stmt = ast.Assign(targets=[stmt.target],
                              value=ast.BinOp(left=copy.deepcopy(stmt.target), op=stmt.op, right=stmt.value))

        if isinstance(stmt, ast.Assign) and _is_self_field_write(stmt, env):
            _write_self_fields(stmt, env)
            continue

        if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            if any(isinstance(n, ast.Attribute) for t in targets for n in ast.walk(t)):
                raise UnsupportedConstructError("writes to object fields are not modelled")

        if isinstance(stmt, ast.Assign):
            if (len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
                    and isinstance(stmt.value, ast.List)):
                env[stmt.targets[0].id] = _list_literal_value(stmt.value, env)
                continue
            if (len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
                    and isinstance(stmt.value, ast.Dict)):
                env[stmt.targets[0].id] = _dict_literal_value(stmt.value, env)
                continue
            enum_value = _enum_operand(stmt.value, env)
            if enum_value is not None and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                env[stmt.targets[0].id] = enum_value  # an enum value is bound as itself, not as a term
                continue
            record = _record_of(stmt.value, env)
            if record is not None and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                _bind_record(env, stmt.targets[0].id, record)
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

        if isinstance(stmt, ast.Try):
            return _exec_try(stmt, env, list(stmts[idx + 1:]), max_unroll)

        if isinstance(stmt, ast.Raise):
            if env.get(_TRY_KEY) is not None:
                raise UnsupportedConstructError("raise inside a try block is not modelled")
            facts = env.setdefault(_FACTS_KEY, [])
            facts.append(z3.Not(_path_of(env)))  # the inputs that reach here raise
            facts.append(_RAISE_NOTE)
            return ("raised", None)

        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            for alias in stmt.names:
                env[alias.asname or alias.name.split(".")[0]] = _OPAQUE
            continue

        if isinstance(stmt, ast.For) and _is_symbolic_range(stmt):
            env.update(_unroll_symbolic_range(stmt, env, max_unroll))
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

            return _branch_flows(cond, then_flow, then_env, else_flow, else_env, env,
                                 list(stmts[idx + 1:]), max_unroll)

        if isinstance(stmt, ast.For) and isinstance(stmt.iter, (ast.Tuple, ast.List)):
            env.update(_unroll_literal_loop(stmt, env, max_unroll))
            continue
        if isinstance(stmt, ast.For) and _is_container_loop(stmt, env):
            env.update(_unroll_container_loop(stmt, env, max_unroll))
            continue

        if isinstance(stmt, ast.For):
            if not (isinstance(stmt.iter, ast.Call)
                    and isinstance(stmt.iter.func, ast.Name)
                    and stmt.iter.func.id == "range"
                    and isinstance(stmt.target, ast.Name)):
                raise UnsupportedConstructError(
                    "only 'for x in range(...)' loops are supported"
                )
            if any(isinstance(n, (ast.Return, ast.Raise)) for n in ast.walk(ast.Module(body=stmt.body, type_ignores=[]))):
                raise UnsupportedConstructError(
                    "'return' or 'raise' inside a loop body is not supported"
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
    facts: Optional[List[Any]] = None,
    exits: Optional[List[Any]] = None,
) -> Any:
    """Symbolically execute a function, returning the Z3 expression for its
    return value. `shared_env` seeds parameter names with shared Z3
    variables so two functions being compared reference the SAME symbolic
    inputs (required for a meaningful equivalence check). Facts that restrict
    the verified domain (see _unroll_container_loop) are appended to `facts`."""
    env = dict(shared_env)
    scope = env.get(_SCOPE_KEY)
    env[_FACTS_KEY] = facts if facts is not None else []
    for arg in func_node.args.args:
        if arg.arg not in env:
            env[arg.arg] = _make_param(_param_kind(arg, func_node.body, scope), arg.arg, env[_FACTS_KEY], scope)
    _with_length_assumptions(env)
    env[_EXITS_KEY] = exits if exits is not None else []
    self_name = _self_name_of(func_node)
    if self_name is not None and isinstance(env.get(self_name), _ObjRef) and env[self_name].is_self:
        # Bind every field the method touches up front, so every branch sees all of
        # them and merges treat them alike.
        obj = env[self_name]
        for attr in sorted(_self_attributes(func_node, self_name)):
            if attr in obj.methods or attr in obj.properties:
                continue  # a method or property is a call, not a field
            env[f"self__{attr}"] = obj.value(attr)
    kinds = [_param_kind(a, func_node.body, scope) for a in func_node.args.args]
    if any(k == "float" or (isinstance(k, tuple) and "float" in k) for k in kinds):
        env[_FACTS_KEY].append(_FLOAT_NOTE)
    if _inferred_bool_params(func_node):
        env[_FACTS_KEY].append(_BOOL_NOTE)
    flow = _exec_stmts(list(func_node.body), env, max_unroll)
    if flow[0] == "raised":
        raise UnsupportedConstructError("every input raises, so there is no result to compare")
    if flow[0] != "return":
        raise UnsupportedConstructError(
            "the function can end without returning a value (None), so there is no value to compare"
        )
    if isinstance(flow[1], _Record):
        return flow[1]  # a function that returns a constructed object; see verify_function_equivalence
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

    env: Dict[str, Any] = {_EXPRESSION_KEY: True}
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
    scope: Any = None,
) -> EquivalenceResult:
    """Prove whether two functions compute the same return value for all
    inputs, within this module's supported subset (see module docstring).
    The two functions are matched positionally by parameter order, not by
    name — `func_a(x, y)` and `func_b(a, b)` are compared with `x`/`a` and
    `y`/`b` bound to the same symbolic variables.

    `scope` resolves the classes and functions the code names (a ProjectScope
    for the file, see project_index.py). Without it, only the definitions in each
    code string are visible. A class-typed or enum parameter is shared only when
    both functions name the same class definition, so keep both in one code string
    or pass one scope; otherwise the two sides are reported as having different types.
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

    owner_a = _method_owner(code_a, func_a, node_a.lineno)
    owner_b = _method_owner(code_b, func_b, node_b.lineno)
    if (owner_a is None) != (owner_b is None) or (owner_a is not None and code_a != code_b):
        return EquivalenceResult(
            status="unsupported",
            reason="methods can only be compared with each other, within one class",
        )
    scope_a = scope if scope is not None else _LocalScope(code_a)
    scope_b = scope_a if scope is not None or code_a == code_b else _LocalScope(code_b)
    try:
        kinds_a = [_param_kind(a, node_a.body, scope_a) for a in node_a.args.args]
        kinds_b = [_param_kind(b, node_b.body, scope_b) for b in node_b.args.args]
    except UnsupportedConstructError as e:
        return EquivalenceResult(status="unsupported", reason=str(e))
    if kinds_a != kinds_b:
        return EquivalenceResult(
            status="unsupported",
            reason=f"parameter types differ: {kinds_a} versus {kinds_b}",
        )
    facts_a: List[Any] = []
    facts_b: List[Any] = []
    # Both sides read the same inputs, so an object or enum parameter is one value for both.
    shared_vars = [_make_param(kind, f"_arg{i}", facts_a, scope_a) for i, kind in enumerate(kinds_a)]
    env_a: Dict[str, Any] = {name: var for name, var in zip(params_a, shared_vars)}
    env_b: Dict[str, Any] = {name: var for name, var in zip(params_b, shared_vars)}
    env_a.update({_SCOPE_KEY: scope_a, _CALL_STACK_KEY: (func_a,), _MAX_UNROLL_KEY: max_unroll})
    env_b.update({_SCOPE_KEY: scope_b, _CALL_STACK_KEY: (func_b,), _MAX_UNROLL_KEY: max_unroll})

    if owner_a is not None:
        # Both methods read the same object, so both sides share one cache of fields.
        fields, cache = _class_fields(owner_a, scope_a), {}
        env_a[params_a[0]] = _ObjRef(fields, cache, facts_a, classdef=owner_a, scope=scope_a, is_self=True)
        env_b[params_b[0]] = _ObjRef(fields, cache, facts_b, classdef=owner_b, scope=scope_b, is_self=True)
    exits_a: List[Any] = []
    exits_b: List[Any] = []
    try:
        result_a = _function_to_symbolic(node_a, env_a, max_unroll, facts_a, exits_a)
        result_b = _function_to_symbolic(node_b, env_b, max_unroll, facts_b, exits_b)
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

    facts = facts_a + facts_b
    assume = z3.And(_input_assumptions(shared_vars), _assume_of(facts))
    claim_a, claim_b = result_a, result_b
    is_record = isinstance(result_a, _Record) or isinstance(result_b, _Record)
    if is_record or owner_a is not None:
        try:
            same_result = _same_result(result_a, result_b)
        except UnsupportedConstructError as e:
            return EquivalenceResult(status="unsupported", reason=str(e))
    if is_record:
        # Records are compared field by field. A claim about them is over the same fields.
        claim_a, claim_b = z3.BoolVal(True), same_result
    if owner_a is not None:
        # Methods are equivalent when they return the same value and leave every field
        # in the same final state. Fields neither side writes keep their initial value.
        same_state = []
        for key in sorted(cache):
            if not isinstance(cache[key], z3.ExprRef):
                continue  # containers and optional fields are never written
            same_state.append(_final_field(exits_a, key, cache[key]) == _final_field(exits_b, key, cache[key]))
        claim_a, claim_b = z3.BoolVal(True), z3.And(same_result, *same_state)
    result = _prove_equal(claim_a, claim_b, assume)
    if result.status == "decided" and result.equivalent is False and any(
            isinstance(f, str) and f == _TYPE_TEST_NOTE for f in facts):
        # The type tests of opaque values are independent unknowns, so the counterexample may
        # assign types that no value has together. It is not a claim about real inputs.
        return EquivalenceResult(status="unsupported", reason=_TYPE_TEST_NOTE)
    result.domain = _notes_of(facts)
    result.proof_a = str(result_a)
    result.proof_b = str(result_b)
    return result


_Z3_PY_BINARY = {
    "+": "+", "-": "-", "*": "*", "/": "/", "div": "//", "mod": "%",
    "<": "<", "<=": "<=", ">": ">", ">=": ">=", "=": "==", "distinct": "!=",
}


def _is_scalar_term(value: Any) -> bool:
    return isinstance(value, z3.ExprRef) and value.sort() in (
        z3.IntSort(), z3.BoolSort(), z3.StringSort(), z3.RealSort())


def _renderable_symbols(param_names: List[str], env: Dict[str, Any], self_name: Optional[str]) -> Dict[str, str]:
    """Z3 symbols of scalar inputs and scalar fields, each mapped to the Python text that names it.

    An enum value and a container are not scalars, so their symbols are absent and cannot
    be rendered: an enum index written as an int would compare unequal to the member, and
    a list length is not an attribute. A field is written `p.attr`, or `<self_name>.attr`
    for the self of a method."""
    out: Dict[str, str] = {}
    for name in param_names:
        value = env.get(name)
        if _is_scalar_term(value) and z3.is_const(value):
            out[value.decl().name()] = name
    for value in env.values():
        if isinstance(value, _ObjRef):
            owner = self_name if value.is_self else value.label
            for attr, term in value.cache.items():
                if _is_scalar_term(term) and z3.is_const(term):
                    out[term.decl().name()] = f"{owner}.{attr}"
    return out


def _render_symbol(symbol: str, names: Any) -> str:
    """The Python text for a Z3 symbol, which must be one of `names`: a dict from symbol to
    text, or a set of names that stand for themselves."""
    if names is None:
        return symbol
    if symbol not in names:
        raise UnsupportedConstructError(f"symbol '{symbol}' is not a scalar parameter or field")
    return names[symbol] if isinstance(names, dict) else symbol


def _z3_to_python(expr: Any, names: Any = None) -> str:
    """Render a Z3 expression as Python source over the same names.

    `names` says which symbols may appear, and how each is written (see
    `_renderable_symbols`), or is a set of parameter names that stand for
    themselves. A symbol outside it (e.g. the stand-in Z3 uses for len(x))
    cannot be rendered, so it raises instead of producing an unbound name.

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
        return _render_symbol(expr.decl().name(), names)

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
    scope: Any = None,
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
    if scope is None:
        scope = _LocalScope(code)
    facts: List[Any] = []
    owner = _method_owner(code, func_name, node.lineno)
    env: Dict[str, Any] = {_SCOPE_KEY: scope, _CALL_STACK_KEY: (func_name,), _MAX_UNROLL_KEY: max_unroll}
    try:
        for i, arg in enumerate(node.args.args):
            if i == 0 and owner is not None:
                env[arg.arg] = _ObjRef(_class_fields(owner, scope), {}, facts,
                                       classdef=owner, scope=scope, is_self=True)
            else:
                env[arg.arg] = _make_param(_param_kind(arg, node.body, scope), arg.arg, facts, scope)
    except UnsupportedConstructError as e:
        return SimplificationResult(status="unsupported", reason=str(e))
    exits: List[Any] = []
    try:
        original = _function_to_symbolic(node, env, max_unroll, facts, exits)
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

    if isinstance(original, _Record):
        return SimplificationResult(
            status="unsupported",
            reason="the function returns an object, which is compared field by field "
                   "(verify_function_equivalence) but has no single simplified expression")
    try:
        simplified = z3.simplify(original)
    except Exception as e:
        return SimplificationResult(status="unsupported", reason=f"Z3 simplify() failed: {e}")

    original_str = str(original)
    simplified_str = str(simplified)
    assumption = z3.And(_input_assumptions(list(env.values())), _assume_of(facts))
    domain = _notes_of(facts)
    self_name = _self_name_of(node)
    if self_name is not None and _writes_fields(node, self_name) and isinstance(env.get(self_name), _ObjRef):
        domain = "; ".join(x for x in (domain, _WRITES_NOTE) if x)

    # Z3 also reorders terms, e.g. "100 + a*50" becomes "100 + 50*a", which is
    # not a simplification. Only a result with fewer nodes is reported.
    if original_str == simplified_str or _z3_size(simplified) >= _z3_size(original):
        return SimplificationResult(status="already_simplest", original_expr=original_str, domain=domain)

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
        renderable = _renderable_symbols([a.arg for a in node.args.args], env, self_name)
        simplified_python = _z3_to_python(simplified, renderable)
    except UnsupportedConstructError:
        simplified_python = None

    return SimplificationResult(
        status="simplified",
        original_expr=original_str,
        simplified_expr=simplified_str,
        simplified_python=simplified_python,
        domain=domain,
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
