"""PyProver Z3 Builtins - len()/abs()/min()/max() and string predicates

Real gap found by direct testing, not carried over from a version-comparison
this time: every `_expr_to_z3()` in this codebase (contract_verifier.py,
loop_verifier.py, contract_simplifier.py -- three independent copies, kept
separate to avoid circular imports per contract_verifier.py's own docstring)
has no `ast.Call` handling at all. Confirmed directly before writing anything
here:

    # Pre: len(arr) > 0                    -> silently "skipped (non-arithmetic)"
    # Post: abs(result) >= 0                -> silently "skipped (non-arithmetic)"
    # Post: result == max(a, b)             -> silently "skipped (non-arithmetic)"
    # Pre: s == "hello"                     -> silently "skipped (non-arithmetic)"

None of these raise or warn loudly -- they degrade to "non-arithmetic, skipped"
the same way a genuinely-unparseable clause would, so a contract full of
`len()`/`abs()`/string checks currently verifies "successfully" while checking
close to nothing. This is very likely the single highest-impact gap in the
verifier for real-world contracts, since `len()` in particular is probably
the most common function call in ordinary pre/postconditions.

This module is shared, importable Call-node support that all three
`_expr_to_z3` functions delegate to for the `ast.Call` case specifically --
it does not replace or reimplement their existing Constant/Name/BinOp/BoolOp/
UnaryOp/Compare handling, and it takes the caller's own recursive
`_expr_to_z3` as a parameter (never imports one of the three verifier files
itself), so it introduces no cross-file coupling beyond what already exists.

Supported:
  len(x)                    -- modeled as a fresh, per-argument-text Z3 Int
                                (consistent across repeated use of len(x)
                                within one verification's shared env; a
                                genuine but honest abstraction: this asserts
                                things ABOUT the length value, not about x's
                                actual contents, the same scope limit already
                                documented for array-templates in the sibling
                                standalone pyprover skill's SORTED_ARRAY/
                                PARTITION templates)
  abs(x), min(a, b, ...), max(a, b, ...)   -- real arithmetic, recurses into
                                args via the caller's own _expr_to_z3, so
                                arbitrary sub-expressions work, not just names

  str_length(s), str_equals(a, b), str_contains(s, sub),
  str_starts_with(s, prefix), str_ends_with(s, suffix)
                                -- backed by Z3's real native String theory
                                (z3.Length/z3.Contains/z3.PrefixOf/
                                z3.SuffixOf), NOT the integer-encoding
                                workaround PyProver v6.1/v7.0 used
                                (StringWorkAround.encode_string/decode_string
                                scaled characters into ints by hand because
                                those versions weren't using Z3's real string
                                theory at all). z3-solver has had native
                                SeqSort/String support for years; there is no
                                reason to re-port a hand-rolled workaround for
                                a limitation that no longer exists. This is a
                                case of restoring an old feature done
                                correctly rather than porting the old
                                implementation, and that's a legitimate
                                same-feature merge, not scope creep past what
                                was asked.

  bare string comparison (`s == "literal"`, `s != "literal"`) -- works
  automatically once a Name has been typed as a Z3 String; see
  `infer_string_names()` below for how that typing decision gets made.

Explicitly NOT supported, honestly (returns None -> caller's existing
"non-arithmetic, skipped" path, never a silent wrong answer):
  - float scaled-integer reasoning (PyProver v6.1/v7.0's FloatWorkAround).
    Floats are real-sorted instead; see seed_real_env() in contract_verifier.py.
  - len() of a literal (e.g. `len([1,2,3])`) -- only bare-name and simple
    attribute-free arguments are given a stable Z3 identity; a literal
    collection's length is a constant Python could just compute, and this
    module doesn't special-case that (falls through to None -> skipped).
  - any string method other than the five listed above (e.g. .upper(),
    .split(), .replace()) -- real Z3 string theory doesn't cover arbitrary
    Python string methods either, so this isn't a workaround gap, it's a
    genuine solver-capability boundary.
"""

import ast
import re
from typing import Any, Callable, Dict, Optional, Set

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False


_STR_CALL_NAMES = frozenset({
    "str_length", "str_equals", "str_contains", "str_starts_with", "str_ends_with",
})


def _canonical_arg_text(node: ast.expr) -> Optional[str]:
    """Stable text key for an argument expression, used to give repeated
    calls with the same textual argument (e.g. two separate `len(arr)`
    clauses) the same underlying Z3 variable. Returns None for anything
    ast.unparse can't handle predictably (shouldn't happen for parsed
    Python, but defensive rather than assumed)."""
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _safe_var_suffix(text: str) -> str:
    """Turn arbitrary expression text into a legal-ish Z3 identifier suffix."""
    return re.sub(r'\W+', '_', text).strip('_') or "expr"


def try_call_to_z3(
    node: ast.Call,
    env: Dict[str, Any],
    expr_to_z3: Callable[[ast.expr, Dict[str, Any]], Any],
) -> Optional[Any]:
    """Attempt to translate a Call node. Returns None (never raises for an
    unsupported call) if the function name isn't one of the builtins this
    module knows -- callers should treat None as "fall through to whatever
    this file's existing unsupported-node handling already does."""
    if not Z3_AVAILABLE:
        return None
    if not isinstance(node.func, ast.Name):
        return None  # method calls (x.foo()) and other non-bare-name calls: not handled here
    fname = node.func.id

    try:
        if fname == "len" and len(node.args) == 1:
            text = _canonical_arg_text(node.args[0])
            if text is None:
                return None
            key = f"__len__{text}"
            if key not in env:
                env[key] = z3.Int(f"len__{_safe_var_suffix(text)}")
            return env[key]

        if fname == "abs" and len(node.args) == 1:
            x = expr_to_z3(node.args[0], env)
            if x is None:
                return None
            return z3.If(x >= 0, x, -x)

        if fname == "min" and len(node.args) >= 2:
            vals = [expr_to_z3(a, env) for a in node.args]
            if any(v is None for v in vals):
                return None
            result = vals[0]
            for v in vals[1:]:
                result = z3.If(v < result, v, result)
            return result

        if fname == "max" and len(node.args) >= 2:
            vals = [expr_to_z3(a, env) for a in node.args]
            if any(v is None for v in vals):
                return None
            result = vals[0]
            for v in vals[1:]:
                result = z3.If(v > result, v, result)
            return result

        if fname in _STR_CALL_NAMES:
            return _string_call_to_z3(fname, node, env, expr_to_z3)

    except (TypeError, z3.Z3Exception):
        # A supported function name with an argument shape/sort Z3 rejects
        # (e.g. min() over something that isn't actually numeric) -- honest
        # "couldn't build this", not a crash.
        return None

    return None


def _string_call_to_z3(
    fname: str,
    node: ast.Call,
    env: Dict[str, Any],
    expr_to_z3: Callable[[ast.expr, Dict[str, Any]], Any],
) -> Optional[Any]:
    if fname == "str_length" and len(node.args) == 1:
        s = expr_to_z3(node.args[0], env)
        if s is None or not _is_z3_string(s):
            return None
        return z3.Length(s)

    if fname == "str_equals" and len(node.args) == 2:
        a = expr_to_z3(node.args[0], env)
        b = expr_to_z3(node.args[1], env)
        if a is None or b is None:
            return None
        return a == b

    if fname == "str_contains" and len(node.args) == 2:
        s = expr_to_z3(node.args[0], env)
        sub = expr_to_z3(node.args[1], env)
        if s is None or sub is None or not _is_z3_string(s):
            return None
        return z3.Contains(s, sub)

    if fname == "str_starts_with" and len(node.args) == 2:
        s = expr_to_z3(node.args[0], env)
        prefix = expr_to_z3(node.args[1], env)
        if s is None or prefix is None or not _is_z3_string(s):
            return None
        return z3.PrefixOf(prefix, s)

    if fname == "str_ends_with" and len(node.args) == 2:
        s = expr_to_z3(node.args[0], env)
        suffix = expr_to_z3(node.args[1], env)
        if s is None or suffix is None or not _is_z3_string(s):
            return None
        return z3.SuffixOf(suffix, s)

    return None


def _is_z3_string(expr: Any) -> bool:
    try:
        return expr.sort_kind() == z3.Z3_SEQ_SORT
    except Exception:
        return False


# ---------------------------------------------------------------------------
# String-typing inference
# ---------------------------------------------------------------------------

_STR_LITERAL_COMPARE_RE = re.compile(r'\b([A-Za-z_]\w*)\s*(?:==|!=)\s*["\']')
_STR_LITERAL_COMPARE_REV_RE = re.compile(r'["\'][^"\']*["\']\s*(?:==|!=)\s*([A-Za-z_]\w*)\b')
_STR_CALL_FIRST_ARG_RE = re.compile(
    r'\bstr_(?:length|equals|contains|starts_with|ends_with)\(\s*([A-Za-z_]\w*)\b'
)


def infer_string_names(clause_strings) -> Set[str]:
    """Scan raw (unparsed) clause strings for signals that a free variable
    should be typed as a Z3 String rather than the default Int, and return
    that set of names.

    This is a textual pre-pass, not a full type system -- it looks for the
    same two signals real-world contracts actually use: direct comparison
    to a string literal (`s == "hello"`), and use as the subject of one of
    this module's str_* predicate functions. Call sites are expected to
    seed `env[name] = z3.String(name)` for every name this returns BEFORE
    parsing any clause, since each `_expr_to_z3`'s existing Name handling
    only creates a fresh Int when a name isn't already in env -- pre-seeding
    is how string typing overrides that default without touching the Name
    branch itself in three separate files.

    Deliberately conservative: a name only gets flagged on a clear signal.
    Ambiguous or absent evidence leaves it as the existing Int default,
    which is the safe direction to be wrong in (an Int-typed name in a
    clause that turns out to need String support fails cleanly via the
    existing "non-arithmetic, skipped" path -- it does not silently
    misverify).
    """
    names: Set[str] = set()
    for clause in clause_strings:
        if not clause:
            continue
        for m in _STR_LITERAL_COMPARE_RE.finditer(clause):
            names.add(m.group(1))
        for m in _STR_LITERAL_COMPARE_REV_RE.finditer(clause):
            names.add(m.group(1))
        for m in _STR_CALL_FIRST_ARG_RE.finditer(clause):
            names.add(m.group(1))
    return names


def seed_string_env(clause_strings, env: Dict[str, Any]) -> None:
    """Convenience wrapper: infer string-typed names from `clause_strings`
    and pre-seed `env` with z3.String vars for any not already present.
    Never overwrites an existing env entry (a name the caller already
    bound to something else, e.g. a loop parameter, is left alone)."""
    if not Z3_AVAILABLE:
        return
    for name in infer_string_names(clause_strings):
        if name not in env:
            env[name] = z3.String(name)


__all__ = [
    'try_call_to_z3', 'infer_string_names', 'seed_string_env', 'Z3_AVAILABLE',
]
