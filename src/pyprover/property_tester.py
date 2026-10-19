"""Property-based testing of Python contracts with Hypothesis.

Restores the Python path of PropertyTester from the standalone PyProver v12.0
(roadmap section 2.4). For each generated input that meets the preconditions,
the function is called and every postcondition is checked on the result.

Limits, on purpose:
- Python only, and only functions whose parameters are plain positional names.
  Every parameter is generated as an integer in [-1000, 1000].
- Clauses are evaluated with a whitelisted AST walker, not eval(). Supported:
  arithmetic, comparisons, and/or/not, and the calls abs, min, max, len.
- The function under test is executed. Only run this on code you trust.
- Hypothesis is optional. Without it the result is "skipped", not "passed".
"""
import ast
from typing import Any, Dict, List, Optional

from .contract_verifier import ContractVerifier, _RESULT_ALIASES, _conditional_parts

try:
    from hypothesis import HealthCheck, assume, given, settings
    from hypothesis import strategies as st
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False

INT_BOUND = 1000
_ALLOWED_CALLS = {"abs": abs, "min": min, "max": max, "len": len}
_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
}
_CMP_OPS = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}


class UnsupportedClause(ValueError):
    """Raised when a contract clause uses syntax the evaluator does not allow."""


class _NotCheckable(Exception):
    """A postcondition could not be evaluated for one input, so that input is discarded."""


def _eval_node(node: ast.expr, env: Dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in _RESULT_ALIASES and "result" in env:
            return env["result"]
        raise UnsupportedClause(f"unknown name '{node.id}'")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left, env), _eval_node(node.right, env))
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, env)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.Not):
            return not operand
    if isinstance(node, ast.BoolOp):
        values = [_eval_node(v, env) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, env)
        for op, comparator in zip(node.ops, node.comparators):
            if type(op) not in _CMP_OPS:
                raise UnsupportedClause(f"comparison {type(op).__name__} not allowed")
            right = _eval_node(comparator, env)
            if not _CMP_OPS[type(op)](left, right):
                return False
            left = right
        return True
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _ALLOWED_CALLS and not node.keywords):
        return _ALLOWED_CALLS[node.func.id](*[_eval_node(a, env) for a in node.args])
    raise UnsupportedClause(f"unsupported syntax: {type(node).__name__}")


def evaluate_clause(clause: str, env: Dict[str, Any]) -> bool:
    """Evaluate a contract clause against env. Raises UnsupportedClause for disallowed syntax."""
    parts = _conditional_parts(clause)
    if parts is not None:  # "if cond: clause" is an implication: true whenever cond is false
        cond_node, then_node = parts
        return (not bool(_eval_node(cond_node, env))) or bool(_eval_node(then_node, env))
    try:
        tree = ast.parse(clause, mode="eval")
    except SyntaxError as e:
        raise UnsupportedClause(f"not a valid expression: {e}") from e
    return bool(_eval_node(tree.body, env))


def _first_function(code: str) -> Optional[ast.FunctionDef]:
    tree = ast.parse(code)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node
    return None


def property_test(code: str, max_examples: int = 200) -> Dict[str, Any]:
    """Check the contract of the first function in code with generated inputs.

    Returns a dict with:
        status:          "passed", "failed" or "skipped"
        examples:        inputs that met the preconditions and were checked
        counterexample:  inputs and the violated clause when status is "failed"
        reason:          why the test was skipped or failed
    """
    if not HYPOTHESIS_AVAILABLE:
        return {"status": "skipped", "reason": "hypothesis is not installed"}

    try:
        fn_node = _first_function(code)
    except SyntaxError as e:
        return {"status": "skipped", "reason": f"syntax error: {e}"}
    if fn_node is None:
        return {"status": "skipped", "reason": "no function definition found"}

    args = fn_node.args
    if args.vararg or args.kwarg or args.kwonlyargs or args.defaults or args.posonlyargs:
        return {"status": "skipped", "reason": "only plain positional parameters are supported"}

    contract = ContractVerifier.parse_contract(code)
    if not contract.postconditions:
        return {"status": "skipped", "reason": "no postconditions to check"}

    params: List[str] = [a.arg for a in args.args]
    probe_env = {p: 0 for p in params}
    try:
        for clause in contract.preconditions + contract.postconditions:
            evaluate_clause(clause, {**probe_env, "result": 0})
    except UnsupportedClause as e:
        return {"status": "skipped", "reason": f"unsupported contract clause: {e}"}
    except Exception:
        pass  # a clause that only fails on some inputs (e.g. division by zero) is handled per example

    namespace: Dict[str, Any] = {}
    exec(compile(ast.Module(body=[fn_node], type_ignores=[]), "<property-test>", "exec"), namespace)
    fn = namespace[fn_node.name]

    state: Dict[str, Any] = {"examples": 0, "failures": []}

    def _violation(inputs: Dict[str, Any]) -> Optional[str]:
        try:
            result = fn(**inputs)
        except Exception as e:
            return f"raised {type(e).__name__}: {e}"
        env = {**inputs, "result": result}
        for clause in contract.postconditions:
            try:
                holds = evaluate_clause(clause, env)
            except Exception:
                raise _NotCheckable() from None  # e.g. division by zero for these inputs
            if not holds:
                return f"postcondition '{clause}' failed"
        return None

    @settings(max_examples=max_examples, deadline=None, database=None,
              suppress_health_check=list(HealthCheck))
    @given(**{p: st.integers(min_value=-INT_BOUND, max_value=INT_BOUND) for p in params})
    def check(**inputs: int) -> None:
        try:
            if not all(evaluate_clause(c, dict(inputs)) for c in contract.preconditions):
                assume(False)
        except UnsupportedClause:
            assume(False)
        state["examples"] += 1
        try:
            problem = _violation(inputs)
        except _NotCheckable:
            assume(False)
        if problem is not None:
            state["failures"].append((dict(inputs), problem))
            raise AssertionError(problem)

    try:
        check()
    except AssertionError:
        inputs, problem = state["failures"][-1]
        return {
            "status": "failed",
            "examples": state["examples"],
            "counterexample": inputs,
            "reason": problem,
        }
    except Exception as e:
        return {
            "status": "skipped",
            "examples": state["examples"],
            "reason": f"hypothesis could not run the property: {type(e).__name__}: {e}",
        }
    return {"status": "passed", "examples": state["examples"], "reason": ""}
