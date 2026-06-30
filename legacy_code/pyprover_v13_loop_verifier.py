"""
RECOVERED FRAGMENT - NOT TESTED IN THIS SESSION
Source: https://claude.ai/chat/f076b379-5374-45c4-a796-67498d72f844
("Code upgrade to version 13")

PyProver Loop Verifier - v13.0

Detects loop invariants from @loop_invariant decorators/comments and
verifies that they hold using Z3:
  - INIT: invariant holds before loop
  - STEP: if invariant holds at start of iteration, it holds at end
  - TERM: loop terminates (via decreasing bound variable)

Supports Python, JavaScript, TypeScript, Java, C, C++, Rust, Go, C#.

This is a more general, multi-language reimplementation of the same idea
prototyped in pyprover_loop_invariant_v2_prototype.py (same folder) - that
earlier version only handled Python AST directly; this one extracts
invariants via regex across many languages' comment syntaxes and verifies
them against an externally-supplied z3 environment (extra_vars), rather than
doing full symbolic execution of the function body itself.

GAP IN RECOVERY: the middle of this file (the actual Z3 INIT/STEP/TERM
proof-obligation construction inside `verify_loop_invariant()`) was not
captured by the search queries used - only the dataclasses, the regex
extraction patterns' start, and the LoopVerifier wrapper class at the end
were recovered. Re-search with "verify_loop_invariant z3 Solver INIT STEP
TERM" to fill the gap.
"""

import re
import z3
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class LoopInvariant:
    """A single loop invariant extracted from source"""
    expression: str
    loop_var: Optional[str] = None       # primary iteration variable (e.g. 'i')
    bound_var: Optional[str] = None      # termination bound (e.g. 'n')
    line_number: Optional[int] = None


@dataclass
class LoopVerificationResult:
    """Result of verifying a single loop invariant"""
    invariant: str
    init_holds: bool = False     # invariant holds before loop
    step_holds: bool = False     # invariant is inductive
    term_holds: bool = False     # loop terminates
    error: Optional[str] = None
    counterexample: Optional[str] = None

    @property
    def fully_verified(self) -> bool:
        return self.init_holds and self.step_holds and self.term_holds


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

_INVARIANT_PATTERNS = [
    # Python: @loop_invariant("expr")
    re.compile(r'@loop_invariant\(["\'](.+?)["\']\)'),
    # C/C++/Java/C#: /*@ loop_invariant expr; @*/
    re.compile(r'/\*@\s*loop_invariant\s+(.+?\)'),
    # GAP: pattern list cut off here mid-regex-literal in the recovered
    # snippet (the C-style pattern above is also missing its closing `*/`
    # in the source as captured - fix before using). Likely more patterns
    # followed for JS/TS, Rust, Go given the docstring claims 9 languages.
]


def extract_loop_invariants(source_code: str) -> List[LoopInvariant]:
    """
    GAP IN RECOVERY: function body not captured by search. Should iterate
    _INVARIANT_PATTERNS against source_code, building LoopInvariant objects
    (with loop_var/bound_var inference, presumably from the nearest
    enclosing `for`/`while` statement). Reconstruct from the two call sites
    below (LoopVerifier.verify_source) and from LoopInvariant's field list.
    """
    raise NotImplementedError("not recovered - see module docstring")


def verify_loop_invariant(
    invariant: LoopInvariant,
    extra_vars: Optional[Dict[str, "z3.ExprRef"]] = None,
    timeout_ms: int = 5000,
) -> LoopVerificationResult:
    """
    GAP IN RECOVERY: this is the actual Hoare-logic core (the INIT/STEP/TERM
    proof construction) and it was NOT captured by the search queries used
    in this session. One fragment found references it raising a
    VerificationError of the form:

        "Add a @loop_invariant with a bound expression or label bound_var."

    suggesting TERM verification requires either an explicit bound
    expression in the invariant or a labeled bound_var, and fails loudly
    rather than guessing. Re-search conversation history for
    "verify_loop_invariant INIT STEP TERM Solver check" to recover the body.
    """
    raise NotImplementedError("not recovered - see function docstring")


class LoopVerifier:
    """
    High-level loop invariant verifier.

    Usage:
        lv = LoopVerifier()
        results = lv.verify_source(source_code)
        for r in results:
            print(r.invariant, r.fully_verified)
    """

    def __init__(self, timeout_ms: int = 5000):
        self.timeout_ms = timeout_ms

    def verify_source(
        self,
        source_code: str,
        extra_vars: Optional[Dict[str, "z3.ExprRef"]] = None
    ) -> List[LoopVerificationResult]:
        """Extract and verify all loop invariants found in source_code."""
        invariants = extract_loop_invariants(source_code)
        return [
            verify_loop_invariant(inv, extra_vars, self.timeout_ms)
            for inv in invariants
        ]

    def summary(self, results: List[LoopVerificationResult]) -> str:
        """Return a human-readable summary of loop invariant results."""
        if not results:
            return "No loop invariants found."
        lines = [f"Loop Invariant Verification ({len(results)} invariant(s)):"]
        for r in results:
            status = "VERIFIED" if r.fully_verified else "PARTIAL" if (r.init_holds or r.step_holds) else "FAILED"
            lines.append(f"  [{status}] {r.invariant}")
            lines.append(f"           INIT={r.init_holds}  STEP={r.step_holds}  TERM={r.term_holds}")
            if r.error:
                lines.append(f"           Note: {r.error}")
        return "\n".join(lines)
