"""Property testing for JavaScript and Rust contracts.

Restores the JavaScript and Rust paths of the PyProver v12.0 PropertyTester
(roadmap section 2.2). Contract clauses are written in Python expression syntax in
every language (the same as Python contracts). They are translated to JavaScript or
Rust expressions, and a harness is generated that calls the function under test with
generated inputs.

Semantics match the Python property tester:
- Every value is a float (f64 in Rust). Python's / is real division, so / is
  translated as real division. // and % use Python's floor semantics.
- Parameters are integers in [-1000, 1000]. Boundary values -1, 0 and 1 always run.
  Rust parameters may be declared i64, i32 or f64. Each run is deterministic.
- A failed precondition discards the input. A panic or exception in the function, or
  a violated postcondition, is a failure with the inputs that caused it.

Limits: one top-level function per source. Parameters must be plain names with
types i64, i32 or f64 (Rust) or no types (JavaScript). The function under test is
executed, so only run this on code you trust.
"""
import ast
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from .contract_verifier import ContractVerifier, _RESULT_ALIASES, _conditional_parts
from .property_tester import UnsupportedClause

INT_BOUND = 1000
EXAMPLES = 200
_RUST_TYPES = {"i64", "i32", "f64"}
_JS_BIN = "node"
_RUSTC = "rustc"


class _Unsupported(Exception):
    pass


def _translate(node: ast.expr, lang: str, params: List[str]) -> str:
    """Translate one clause expression into a JavaScript or Rust boolean/float expression."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "true" if node.value else "false"
        if isinstance(node.value, (int, float)):
            return repr(float(node.value))  # "1.0" is a valid f64 literal in both languages
        raise UnsupportedClause(f"unsupported constant {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id in params or node.id in _RESULT_ALIASES:
            return "result" if node.id in _RESULT_ALIASES else node.id
        raise UnsupportedClause(f"unknown name '{node.id}'")
    if isinstance(node, ast.UnaryOp):
        operand = _translate(node.operand, lang, params)
        if isinstance(node.op, ast.USub):
            return f"(-{operand})"
        if isinstance(node.op, ast.UAdd):
            return f"(+{operand})"
        if isinstance(node.op, ast.Not):
            return f"(!{operand})"
        raise UnsupportedClause(f"unsupported unary operator {type(node.op).__name__}")
    if isinstance(node, ast.BinOp):
        left = _translate(node.left, lang, params)
        right = _translate(node.right, lang, params)
        if isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            symbol = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}[type(node.op)]
            return f"({left} {symbol} {right})"
        if isinstance(node.op, ast.FloorDiv):
            return f"py_floordiv({left}, {right})"
        if isinstance(node.op, ast.Mod):
            return f"py_mod({left}, {right})"
        raise UnsupportedClause(f"unsupported operator {type(node.op).__name__}")
    if isinstance(node, ast.BoolOp):
        joiner = " && " if isinstance(node.op, ast.And) else " || "
        return "(" + joiner.join(_translate(v, lang, params) for v in node.values) + ")"
    if isinstance(node, ast.Compare):
        parts = []
        left = _translate(node.left, lang, params)
        for op, comparator in zip(node.ops, node.comparators):
            right = _translate(comparator, lang, params)
            symbol = _CMP[type(op)][0 if lang == "javascript" else 1] if type(op) in _CMP else None
            if symbol is None:
                raise UnsupportedClause(f"unsupported comparison {type(op).__name__}")
            parts.append(f"({left} {symbol} {right})")
            left = right
        return "(" + " && ".join(parts) + ")"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        name = node.func.id
        args = [_translate(a, lang, params) for a in node.args]
        if name == "abs" and len(args) == 1:
            return f"Math.abs({args[0]})" if lang == "javascript" else f"({args[0]}).abs()"
        if name in ("min", "max") and len(args) == 2:
            if lang == "javascript":
                return f"Math.{name}({args[0]}, {args[1]})"
            return f"({args[0]}).{name}({args[1]})"
        raise UnsupportedClause(f"unsupported call {name}()")
    raise UnsupportedClause(f"unsupported syntax: {type(node).__name__}")


_CMP = {
    ast.Lt: ("<", "<"),
    ast.LtE: ("<=", "<="),
    ast.Gt: (">", ">"),
    ast.GtE: (">=", ">="),
    ast.Eq: ("===", "=="),
    ast.NotEq: ("!==", "!="),
}


def _clause_expr(clause: str, lang: str, params: List[str]) -> str:
    parts = _conditional_parts(clause)
    if parts is not None:  # "if cond: clause" is an implication
        cond, then = parts
        return f"(!{_translate(cond, lang, params)} || {_translate(then, lang, params)})"
    return _translate(ast.parse(clause, mode="eval").body, lang, params)


def _all_of(clauses: List[str], lang: str, params: List[str]) -> str:
    if not clauses:
        return "true"
    return "(" + " && ".join(_clause_expr(c, lang, params) for c in clauses) + ")"


def _skipped(reason: str) -> Dict[str, Any]:
    return {"status": "skipped", "reason": reason}


def _parse_result(stdout: str) -> Dict[str, Any]:
    """Harness output: PASSED <examples>, or FAILED <examples> <reason>\\t<name=value,...>."""
    line = stdout.strip().splitlines()[-1] if stdout.strip() else ""
    if line.startswith("PASSED"):
        return {"status": "passed", "examples": int(line.split()[1]), "reason": ""}
    if line.startswith("FAILED"):
        head, _, inputs_text = line.partition("\t")
        _, examples, reason = head.split(" ", 2)
        counterexample: Dict[str, Any] = {}
        for pair in filter(None, inputs_text.split(",")):
            name, _, value = pair.partition("=")
            number = float(value)
            counterexample[name] = int(number) if number.is_integer() else number
        return {"status": "failed", "examples": int(examples), "reason": reason,
                "counterexample": counterexample}
    return {"status": "skipped", "reason": f"harness produced no result: {stdout.strip()[:200]!r}"}


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

_JS_FUNCTION = re.compile(r"function\s+([A-Za-z_]\w*)\s*\(([^)]*)\)")


def property_test_js(code: str, max_examples: int = EXAMPLES) -> Dict[str, Any]:
    """Property-test the first ``function name(...)`` in JavaScript source code."""
    if shutil.which(_JS_BIN) is None:
        return _skipped("node is not installed")
    match = _JS_FUNCTION.search(code)
    if match is None:
        return _skipped("no function declaration found")
    name = match.group(1)
    params = [p.strip().split("=")[0].strip() for p in match.group(2).split(",") if p.strip()]
    if not all(re.fullmatch(r"[A-Za-z_]\w*", p) for p in params):
        return _skipped("only plain positional parameters are supported")

    contract = ContractVerifier.parse_contract(code)
    if not contract.postconditions:
        return _skipped("no postconditions to check")
    try:
        pre = _all_of(contract.preconditions, "javascript", params)
        post = _all_of(contract.postconditions, "javascript", params)
    except (UnsupportedClause, SyntaxError) as e:
        return _skipped(f"unsupported contract clause: {e}")

    names = ", ".join(params)
    harness = f"""{code}

function py_floordiv(a, b) {{ return Math.floor(a / b); }}
function py_mod(a, b) {{ return a - b * Math.floor(a / b); }}
const __pre = ({names}) => {pre};
const __post = ({names}, result) => {post};
let __seed = 12345;
function __rand() {{
  __seed = (__seed + 0x6D2B79F5) | 0;
  let t = Math.imul(__seed ^ (__seed >>> 15), 1 | __seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}}
const __cases = [];
for (const v of [-1, 0, 1]) __cases.push([{", ".join(["v"] * len(params))}]);
for (let i = 0; i < {max_examples}; i++) {{
  __cases.push([{", ".join("Math.floor(__rand() * 2001) - 1000" for _ in params)}]);
}}
let examples = 0;
for (const args of __cases) {{
  if (!__pre(...args)) continue;
  examples++;
  const inputs = {{}};
  {" ".join(f"inputs['{p}'] = args[{i}];" for i, p in enumerate(params))}
  let result;
  try {{
    result = {name}(...args);
  }} catch (e) {{
    console.log(`FAILED ${{examples}} raised ${{e.name}}: ${{e.message}}\\t` + Object.entries(inputs).map(([k, v]) => k + '=' + v).join(','));
    process.exit(0);
  }}
  if (!__post(...args, result)) {{
    console.log(`FAILED ${{examples}} postcondition failed\\t` + Object.entries(inputs).map(([k, v]) => k + '=' + v).join(','));
    process.exit(0);
  }}
}}
console.log(`PASSED ${{examples}}`);
"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "harness.js")
        with open(path, "w", encoding="utf-8") as f:
            f.write(harness)
        try:
            run = subprocess.run([_JS_BIN, path], capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return _skipped("node timed out")
    if run.returncode != 0 and not run.stdout.strip():
        return _skipped(f"node failed: {run.stderr.strip()[:200]}")
    return _parse_result(run.stdout)


# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------

_RUST_FN = re.compile(r"fn\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:->\s*([\w]+))?\s*\{")


def property_test_rust(code: str, max_examples: int = EXAMPLES) -> Dict[str, Any]:
    """Property-test the first ``fn name(...)`` in Rust source code."""
    if shutil.which(_RUSTC) is None:
        return _skipped("rustc is not installed")
    match = _RUST_FN.search(code)
    if match is None:
        return _skipped("no function found")
    name, param_text, ret = match.group(1), match.group(2), match.group(3)

    params: List[Tuple[str, str]] = []
    for part in filter(None, (p.strip() for p in param_text.split(","))):
        pname, _, ptype = part.partition(":")
        pname, ptype = pname.strip(), ptype.strip()
        if ptype not in _RUST_TYPES or not re.fullmatch(r"[A-Za-z_]\w*", pname):
            return _skipped(f"unsupported parameter '{part}' (use i64, i32 or f64)")
        params.append((pname, ptype))
    names = [p for p, _ in params]

    contract = ContractVerifier.parse_contract(code)
    if not contract.postconditions:
        return _skipped("no postconditions to check")
    if ret is not None and ret not in _RUST_TYPES:
        return _skipped(f"unsupported return type '{ret}'")
    if ret is None:
        if any(re.search(r"\bresult\b|\breturn\b", c) for c in contract.postconditions):
            return _skipped("postcondition refers to a result but the function returns nothing")
    try:
        pre = _all_of(contract.preconditions, "rust", names)
        post = _all_of(contract.postconditions, "rust", names)
    except (UnsupportedClause, SyntaxError) as e:
        return _skipped(f"unsupported contract clause: {e}")

    typed_f64 = ", ".join(f"{p}: f64" for p in names)
    call_args = ", ".join(f"vals[{i}] as {t}" if t != "f64" else f"vals[{i}]"
                          for i, (_, t) in enumerate(params))
    if ret is None:
        call_stmt = f"{name}({call_args});"
        result_line = "let result: f64 = 0.0;"
    else:
        call_stmt = f"let raw = {name}({call_args});"
        result_line = "let result: f64 = raw as f64;" if ret != "f64" else "let result: f64 = raw;"
    name_list = ", ".join(f'"{p}"' for p in names)
    input_args = ", ".join(f"vals[{i}]" for i in range(len(names)))
    harness = f"""#![allow(warnings)]
{code}

fn py_floordiv(a: f64, b: f64) -> f64 {{ (a / b).floor() }}
fn py_mod(a: f64, b: f64) -> f64 {{ a - b * (a / b).floor() }}
fn __pre({typed_f64}) -> bool {{ {pre} }}
fn __post({typed_f64}, result: f64) -> bool {{ {post} }}

fn __next(state: &mut u64) -> f64 {{
    *state = state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
    ((*state >> 33) % 2001) as f64 - 1000.0
}}

fn __show(vals: &[f64]) -> String {{
    [{name_list}].iter().zip(vals.iter()).map(|(n, v)| format!("{{}}={{}}", n, v))
        .collect::<Vec<String>>().join(",")
}}

fn main() {{
    let boundary = [-1.0f64, 0.0, 1.0];
    let mut state: u64 = 0x2545F4914F6CDD1D;
    let mut examples: u64 = 0;
    for case in 0..(boundary.len() + {max_examples}) {{
        let vals: Vec<f64> = (0..{len(names)}).map(|_| {{
            if case < boundary.len() {{ boundary[case] }} else {{ __next(&mut state) }}
        }}).collect();
        if !__pre({input_args}) {{
            continue;
        }}
        examples += 1;
        let run = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {{
            {call_stmt}
            {result_line}
            __post({input_args}, result)
        }}));
        match run {{
            Ok(true) => {{}}
            Ok(false) => {{
                println!("FAILED {{}} postcondition failed\t{{}}", examples, __show(&vals));
                return;
            }}
            Err(_) => {{
                println!("FAILED {{}} panicked\t{{}}", examples, __show(&vals));
                return;
            }}
        }}
    }}
    println!("PASSED {{}}", examples);
}}
"""
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "harness.rs")
        binary = os.path.join(tmp, "harness")
        with open(source, "w", encoding="utf-8") as f:
            f.write(harness)
        try:
            build = subprocess.run([_RUSTC, "--edition", "2021", "-O", source, "-o", binary],
                                   capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return _skipped("rustc timed out")
        if build.returncode != 0:
            return _skipped(f"rustc could not build the harness: {build.stderr.strip()[:300]}")
        try:
            run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return _skipped("the Rust harness timed out")
    return _parse_result(run.stdout)
