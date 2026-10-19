"""Verify a bug fix: "bugs found -> tests generated -> verify fix".

The original code must fail its contract on generated inputs (the bug is
reproduced with a counterexample). The fixed code must then pass the same
contract on generated inputs, and the formal verifier must not reject it.
Code without postconditions cannot be checked this way and is reported as
not verified.

Supports Python, JavaScript (node) and Rust (rustc). Running the property check executes the function under test, so only use this
on code you trust (see pyprover/property_tester.py).
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..pyprover.contract_verifier import Z3_AVAILABLE, ContractVerifier
from ..pyprover.property_tester import property_test
from ..pyprover.property_tester_lang import property_test_js, property_test_rust

_RUNNERS = {
    "python": property_test,
    "javascript": property_test_js,
    "rust": property_test_rust,
}


@dataclass
class FixVerification:
    fix_verified: bool
    bug_reproduced: bool
    counterexample: Optional[Dict[str, Any]]
    fixed_status: str        # "passed", "failed" or "skipped" for the fixed code
    fixed_examples: int
    formal_verified: Optional[bool]
    reason: str


def verify_fix(original_code: str, fixed_code: str, language: str = "python",
               max_examples: int = 200) -> FixVerification:
    if language not in _RUNNERS:
        raise ValueError(f"unsupported language {language!r}; expected one of {sorted(_RUNNERS)}")
    run = _RUNNERS[language]
    before = run(original_code, max_examples=max_examples)
    if before["status"] == "skipped":
        return FixVerification(
            fix_verified=False, bug_reproduced=False, counterexample=None,
            fixed_status="not_run", fixed_examples=0, formal_verified=None,
            reason=f"cannot test the original code: {before['reason']}",
        )
    if before["status"] == "passed":
        return FixVerification(
            fix_verified=False, bug_reproduced=False, counterexample=None,
            fixed_status="not_run", fixed_examples=0, formal_verified=None,
            reason="the original code passed its contract; no bug reproduced, so there is nothing to fix",
        )

    after = run(fixed_code, max_examples=max_examples)
    formal = ContractVerifier.verify_contract(fixed_code)["verified"] if Z3_AVAILABLE else None
    fixed_ok = after["status"] == "passed" and formal is not False

    if fixed_ok:
        reason = f"bug reproduced by {before['counterexample']}; the fix passes {after['examples']} generated inputs"
    elif after["status"] == "failed":
        reason = f"the fix still violates the contract on {after['counterexample']}"
    elif after["status"] == "skipped":
        reason = f"cannot test the fixed code: {after['reason']}"
    else:
        reason = "the formal verifier rejects the fixed code"

    return FixVerification(
        fix_verified=fixed_ok,
        bug_reproduced=True,
        counterexample=before["counterexample"],
        fixed_status=after["status"],
        fixed_examples=after.get("examples", 0),
        formal_verified=formal,
        reason=reason,
    )
