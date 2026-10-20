"""
RECOVERED FRAGMENT - NOT TESTED IN THIS SESSION
Source: https://claude.ai/chat/11506dad-69d9-49f6-890d-b240a5768aa1
("Proof programming and JavaScript compatibility")

This is the earliest known prototype of loop-invariant verification in the
PyProver lineage - predates the v6.x/v8.x/v13.x branches documented in
roadmap.md §1. It demonstrates the core Hoare-logic technique (INIT +
PRESERVATION proof obligations, then constraining post-loop state to
"invariant AND NOT loop_condition") that v13.0's loop_verifier.py later
reimplemented in a more general, multi-language form
(see pyprover_v13_loop_verifier.py in this folder).

Recovered as two non-contiguous snippets from the same chat; the gap between
them (the body of `loop_invariant()` the decorator, and most of `ASTToZ3`)
was NOT recovered by the search queries used and would need re-fetching via
conversation_search with more targeted queries (e.g. "ASTToZ3 visit_While
ForAll Implies translate") before this is usable standalone.
"""

import ast
import inspect
import textwrap
import functools
from typing import Callable, List
from z3 import (
    Int, Bool, Real, And, Or, Not, Implies, ForAll,
    Solver, sat, unsat, unknown, Z3Exception,
    IntVal, BoolVal, ArithRef, BoolRef, If,
    Array, IntSort, Select, Store,
)


# ---------------------------------------------------------------------------
# Contract storage
# ---------------------------------------------------------------------------

class ContractError(Exception):
    pass

class VerificationError(Exception):
    pass

_contracts: dict = {}

def _init_contract(name):
    if name not in _contracts:
        _contracts[name] = {"requires": [], "ensures": [], "loop_invariants": []}


def requires(condition_str: str):
    """Precondition decorator."""
    def decorator(fn):
        name = fn.__qualname__
        _init_contract(name)
        _contracts[name]["requires"].append(condition_str)
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        wrapper.__qualname__ = name
        return wrapper
    return decorator


def ensures(condition_str: str):
    """Postcondition decorator. Use 'result' to refer to the return value."""
    def decorator(fn):
        name = fn.__qualname__
        _init_contract(name)
        _contracts[name]["ensures"].append(condition_str)
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        wrapper.__qualname__ = name
        return wrapper
    return decorator


def loop_invariant(invariant_str: str):
    """
    Loop invariant decorator. The invariant must hold:
      1. Before the loop (initiation)
      2. After each iteration given it held before (preservation)
    After the loop we know: invariant AND NOT loop_condition.
    """
    # NOTE: body of this decorator not recovered by search - it presumably
    # appends to _contracts[name]["loop_invariants"] the same way
    # requires()/ensures() append to their lists. Reconstruct by analogy
    # before relying on this.
    raise NotImplementedError("decorator body not recovered - see docstring")


# ---------------------------------------------------------------------------
# Symbolic executor (Hoare-logic core)
# ---------------------------------------------------------------------------

def _find_modified_vars(stmts: list) -> set:
    modified = set()
    for node in ast.walk(ast.Module(body=stmts, type_ignores=[])):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    modified.add(t.id)
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                modified.add(node.target.id)
    return modified


class SymbolicExecutor(ast.NodeVisitor):
    def __init__(self, z3_vars: dict, loop_invariants: list = None):
        self.env             = dict(z3_vars)
        self.translator      = ASTToZ3(self.env)  # NOTE: ASTToZ3 class itself not recovered
        self._return_value   = None
        self.loop_invariants = loop_invariants or []
        self.proof_obligations: list = []
        self.extra_assumptions: list = []

    def execute(self, func_body: list):
        for stmt in func_body:
            self.visit(stmt)
            if self._return_value is not None:
                return self._return_value
        raise VerificationError("Function has no return statement")

    def visit_Return(self, node):
        self._return_value = self.translator.visit(node.value)

    def visit_Assign(self, node):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise NotImplementedError("Only simple name assignments supported")
        name = node.targets[0].id
        val  = self.translator.visit(node.value)
        self.env[name] = val
        self.translator.vars = self.env

    def visit_AugAssign(self, node):
        if not isinstance(node.target, ast.Name):
            raise NotImplementedError("Only simple augmented assignments supported")
        name  = node.target.id
        old   = self.env[name]
        delta = self.translator.visit(node.value)
        op    = node.op
        if   isinstance(op, ast.Add):  self.env[name] = old + delta
        elif isinstance(op, ast.Sub):  self.env[name] = old - delta
        elif isinstance(op, ast.Mult): self.env[name] = old * delta
        else: raise NotImplementedError(f"AugAssign {type(op).__name__}")
        self.translator.vars = self.env

    def visit_If(self, node):
        cond = self.translator.visit(node.test)

        then_exec = SymbolicExecutor(dict(self.env), self.loop_invariants)
        then_ret  = then_exec.execute(node.body) if node.body else None

        else_exec = SymbolicExecutor(dict(self.env), self.loop_invariants)
        else_ret  = else_exec.execute(node.orelse) if node.orelse else None

        self.proof_obligations += then_exec.proof_obligations + else_exec.proof_obligations
        self.extra_assumptions += then_exec.extra_assumptions + else_exec.extra_assumptions

        if then_ret is not None and else_ret is not None:
            self._return_value = If(cond, then_ret, else_ret)
        elif then_ret is not None:
            self._return_value = then_ret
        elif else_ret is not None:
            self._return_value = else_ret

    def visit_While(self, node):
        """
        The Hoare-logic core: a loop with no @loop_invariant is rejected
        outright (formal verification can't reason about an unbounded loop
        without one). With an invariant I, three proof obligations are
        generated:

          1. INITIATION:   I holds at loop entry, given the env so far.
          2. PRESERVATION: assuming I and the loop condition hold at the
             start of an arbitrary iteration (using fresh symbolic
             "kth iteration" values for every variable the loop body
             modifies), running the body once still leaves I holding.
          3. POST-LOOP:    after the loop, the caller may assume
             I AND NOT loop_condition (fresh "post" symbolic values),
             which becomes an extra assumption for the rest of the function.
        """
        if not self.loop_invariants:
            raise VerificationError(
                "While loop has no @loop_invariant. "
                "Add @loop_invariant('your_invariant') to verify this function."
            )

        inv_strs = self.loop_invariants

        # INITIATION: invariant holds at loop entry (current env)
        entry_tr  = ASTToZ3(dict(self.env))
        entry_inv = And(*[entry_tr.translate(s) for s in inv_strs])
        self.proof_obligations.append({
            "name": "invariant holds at loop entry (initiation)",
            "pre":  BoolVal(True),   # global preconditions added in verify()
            "post": entry_inv,
        })

        # PRESERVATION: assume fresh vars satisfying I and C, run body, check I still holds
        modified  = _find_modified_vars(node.body)
        fresh_env = dict(self.env)
        for v in modified:
            if v in fresh_env:
                fresh_env[v] = Int(f"{v}__k")   # symbolic "kth iteration" value

        fresh_tr   = ASTToZ3(fresh_env)
        fresh_inv  = And(*[fresh_tr.translate(s) for s in inv_strs])
        fresh_cond = fresh_tr.visit(node.test)

        body_exec = SymbolicExecutor(dict(fresh_env), [])
        for stmt in node.body:
            body_exec.visit(stmt)
            if body_exec._return_value is not None:
                break

        post_tr  = ASTToZ3(body_exec.env)
        post_inv = And(*[post_tr.translate(s) for s in inv_strs])

        self.proof_obligations.append({
            "name": "invariant preserved by loop body (preservation)",
            "pre":  And(fresh_inv, fresh_cond),
            "post": post_inv,
        })

        # POST-LOOP: update env to fresh post-loop symbols constrained by I and NOT C
        post_env = dict(self.env)
        for v in modified:
            if v in post_env:
                post_env[v] = Int(f"{v}__post")

        post_tr    = ASTToZ3(post_env)
        post_inv_e = And(*[post_tr.translate(s) for s in inv_strs])
        post_cond  = post_tr.visit(node.test)

        self.extra_assumptions.append(And(post_inv_e, Not(post_cond)))
        self.env = post_env
        self.translator.vars = self.env

    def visit_Pass(self, node):
        pass

    def generic_visit(self, node):
        raise NotImplementedError(
            f"Statement '{type(node).__name__}' not supported. "
            "Loops need @loop_invariant; comprehensions/try/class are out of scope."
        )


# NOTE: `ASTToZ3` class (the expression translator referenced throughout
# above) was not recovered by the search queries used in this session.
# Its method signatures used here are: __init__(self, z3_vars: dict),
# .translate(expr_str: str) -> z3 expr, .visit(ast_node) -> z3 expr,
# and a settable .vars attribute. Re-search conversation history for
# "ASTToZ3 class visit_BinOp visit_Compare" to recover it before using
# this fragment.
