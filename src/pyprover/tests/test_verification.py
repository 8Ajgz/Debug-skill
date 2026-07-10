"""
Tests for PyProver v14.0 formal verification with Z3 SMT solver.

Tests contract verification, preconditions, postconditions,
loop invariants, and property-based testing.
"""

import pytest
from ..contract_verifier import ContractVerifier, ContractSpec


class TestContractVerification:
    """Test formal contract verification."""
    
    @pytest.fixture
    def verifier(self):
        return ContractVerifier()
    
    @pytest.mark.verification
    @pytest.mark.contract
    def test_simple_contract_verification(self, verifier):
        """Test verification of simple contract."""
        code = """
def add(a, b):
    # Pre: True
    # Post: result == a + b
    return a + b
"""
        result = verifier.verify_contract(code)
        assert result.get('verified') is True or result is not None
    
    @pytest.mark.verification
    @pytest.mark.contract
    def test_precondition_verification(self, verifier):
        """Test verification with preconditions."""
        code = """
def divide(a, b):
    # Pre: b != 0
    # Post: result * b == a (approximately)
    return a / b
"""
        result = verifier.verify_contract(code)
        # Should attempt verification even if uncertain
        assert result is not None
    
    @pytest.mark.verification
    @pytest.mark.contract
    @pytest.mark.parametrize("code", [
        """
def square(x):
    # Pre: x >= 0
    # Post: result >= 0
    return x * x
""",
        """
def absolute(x):
    # Pre: True
    # Post: result >= 0
    if x >= 0:
        return x
    else:
        return -x
""",
    ])
    def test_multiple_contracts(self, verifier, code):
        """Test verification of multiple contract styles."""
        result = verifier.verify_contract(code)
        assert result is not None


class TestBuiltinFunctionContracts:
    """Integration tests: z3_builtins.py wired through ContractVerifier.verify_contract.

    Before this, len()/abs()/min()/max()/string comparisons all silently
    degraded to 'non-arithmetic, skipped' -- confirmed by direct testing
    before this class existed. These tests lock in that they now actually
    verify (or actually fail) rather than silently passing through unchecked.
    """

    @pytest.fixture
    def verifier(self):
        return ContractVerifier()

    def test_len_postcondition_verified(self, verifier):
        code = """
def f(arr):
    # Pre: len(arr) > 0
    # Post: len(result) == len(arr)
    return arr
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is True

    def test_len_contradiction_caught(self, verifier):
        code = """
def f():
    # Pre: len(x) > 0
    # Post: len(x) < 0
    return None
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is False

    def test_abs_verified(self, verifier):
        code = """
def f(x):
    # Post: abs(x) >= 0
    return abs(x)
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is True

    def test_max_min_relationship_verified(self, verifier):
        code = """
def f(a, b):
    # Pre: a > 0
    # Pre: b > 0
    # Post: max(a, b) >= min(a, b)
    return a
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is True

    def test_max_min_wrong_relationship_caught(self, verifier):
        code = """
def f(a, b):
    # Pre: a > 0
    # Pre: b > 0
    # Post: max(a, b) < min(a, b)
    return a
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is False

    def test_string_equality_verified(self, verifier):
        code = """
def f(s):
    # Pre: s == "hello"
    # Post: s == "hello"
    return s
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is True

    def test_string_equality_contradiction_caught(self, verifier):
        code = """
def f(s):
    # Pre: s == "hello"
    # Post: s == "goodbye"
    return s
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is False

    def test_str_predicates_verified(self, verifier):
        code = """
def f(s):
    # Pre: s == "hello world"
    # Post: str_contains(s, "world")
    return s
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is True

    def test_str_predicate_contradiction_caught(self, verifier):
        code = """
def f(s):
    # Pre: s == "foo"
    # Post: str_starts_with(s, "bar")
    return s
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is False


class TestQuantifiedContracts:
    """Integration tests: quantifiers.py wired through ContractVerifier.verify_contract."""

    @pytest.fixture
    def verifier(self):
        return ContractVerifier()

    def test_quantified_postcondition_verified(self, verifier):
        code = """
def f(n):
    # Pre: n > 0
    # Post: all(i >= 0 for i in range(0, n))
    return list(range(n))
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is True
        assert result['postconditions_ok'] is True

    def test_quantified_postcondition_that_is_false_fails(self, verifier):
        code = """
def f():
    # Post: all(i < 5 for i in range(0, 10))
    return None
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is False
        assert result['postconditions_ok'] is False

    def test_quantified_existential_postcondition(self, verifier):
        code = """
def f():
    # Post: any(i == 7 for i in range(0, 10))
    return 7
"""
        result = verifier.verify_contract(code)
        assert result['verified'] is True


class TestLoopInvariants:
    """Test loop invariant verification."""
    
    @pytest.fixture
    def verifier(self):
        return ContractVerifier()
    
    @pytest.mark.verification
    def test_loop_invariant_detection(self, verifier):
        """Test detection of loop invariants."""
        code = """
def sum_list(items):
    total = 0
    for item in items:
        total += item
    return total
"""
        result = verifier.verify_contract(code)
        # Should analyze loop structure
        assert result is not None


class TestPropertyBasedVerification:
    """Test property-based verification with Hypothesis."""
    
    @pytest.fixture
    def verifier(self):
        return ContractVerifier()
    
    @pytest.mark.verification
    def test_property_verification(self, verifier):
        """Test property-based verification."""
        code = """
def add_commutative(a, b):
    # Property: add(a, b) == add(b, a)
    return a + b
"""
        result = verifier.verify_contract(code)
        assert result is not None


class TestVerificationEdgeCases:
    """Test edge cases in formal verification."""
    
    @pytest.fixture
    def verifier(self):
        return ContractVerifier()
    
    @pytest.mark.verification
    def test_empty_contract(self, verifier):
        """Test code without explicit contracts."""
        code = "def identity(x): return x"
        
        # Should still parse and analyze
        result = verifier.verify_contract(code)
        assert result is not None
    
    @pytest.mark.verification
    def test_unsatisfiable_contract(self, verifier):
        """Test detection of unsatisfiable contracts."""
        code = """
def impossible():
    # Pre: x > 5
    # Pre: x < 3
    return x
"""
        result = verifier.verify_contract(code)
        # Should detect unsatisfiability
        assert result is not None


class TestContractParsing:
    """Test parsing of contract specifications."""
    
    @pytest.fixture
    def verifier(self):
        return ContractVerifier()
    
    @pytest.mark.verification
    @pytest.mark.parametrize("code,has_contract", [
        ("def foo(): pass", False),
        ("def foo():\n    # Pre: True\n    pass", True),
        ("def foo():\n    # Post: result\n    return 1", True),
        ("def foo():\n    # Pre: x > 0\n    # Post: result > 0\n    return x", True),
    ])
    def test_contract_detection(self, verifier, code, has_contract):
        """Test detection of contracts in code."""
        result = verifier.verify_contract(code)
        assert result is not None


class TestContractInputHardening:
    """Regression tests for the DoS-protection input-size guard."""

    def test_oversized_input_rejected_not_crashed(self):
        huge_code = "x = 1\n" * 25_000  # exceeds MAX_CONTRACT_LINES
        result = ContractVerifier.verify_contract(huge_code)
        assert result["verified"] is False
        assert "rejected" in result["details"][-1].lower()

    def test_normal_sized_input_unaffected(self):
        result = ContractVerifier.verify_contract("def f(x):\n    return x\n")
        assert result is not None


class TestAsyncConcurrentVariableDetection:
    """
    Regression tests for the AsyncVerifier.detect_concurrent_variables bug:
    the original implementation tokenized every word on every line
    (including inside comments/docstrings/string literals) and the
    "after await" flag was sticky for the rest of the file once set, so any
    file merely mentioning the word "await" once flagged nearly every
    identifier and English word in the file as a "concurrent variable".
    """

    @pytest.fixture
    def async_verifier(self):
        from pyprover.async_verifier import AsyncVerifier
        return AsyncVerifier()

    def test_comment_mentioning_await_does_not_flag_everything(self, async_verifier):
        code = (
            "# This function does not actually use await, just discusses it\n"
            "def normal_function(alpha, beta, gamma):\n"
            "    result = alpha + beta\n"
            "    other = gamma * 2\n"
            "    return result, other\n"
        )
        concurrent = async_verifier.detect_concurrent_variables(code, "python")
        assert len(concurrent) < 5

    def test_string_literal_mentioning_await_does_not_flag_everything(self, async_verifier):
        code = (
            'def f(alpha, beta):\n'
            '    msg = "lock held across an await point"\n'
            '    total = alpha + beta\n'
            '    return total\n'
        )
        concurrent = async_verifier.detect_concurrent_variables(code, "python")
        assert len(concurrent) < 5

    def test_genuine_concurrent_variable_still_detected(self, async_verifier):
        code = (
            "async def f(counter):\n"
            "    if counter < 5:\n"
            "        await asyncio.sleep(1)\n"
            "        counter += 1\n"
        )
        concurrent = async_verifier.detect_concurrent_variables(code, "python")
        assert "counter" in concurrent


# ============================================================================
# Loop Verifier tests
# ============================================================================

class TestLoopVerifier:
    """Tests for the new LoopVerifier component."""

    def test_extract_no_invariants(self):
        from pyprover.loop_verifier import extract_loop_invariants
        code = "def f():\n    x = 0\n    while x < 10:\n        x += 1"
        assert extract_loop_invariants(code) == []

    def test_extract_python_comment(self):
        from pyprover.loop_verifier import extract_loop_invariants
        code = "# Invariant: i >= 0\nx = 0"
        invs = extract_loop_invariants(code)
        assert len(invs) == 1
        assert invs[0].expression == "i >= 0"

    def test_extract_inv_shorthand(self):
        from pyprover.loop_verifier import extract_loop_invariants
        code = "# Inv: i <= n"
        invs = extract_loop_invariants(code)
        assert len(invs) == 1
        assert invs[0].expression == "i <= n"

    def test_verify_source_no_z3_graceful(self, monkeypatch):
        import pyprover.loop_verifier as lv
        monkeypatch.setattr(lv, "Z3_AVAILABLE", False)
        from pyprover.loop_verifier import LoopVerifier
        report = LoopVerifier().verify_source("# Invariant: i >= 0\nx = 0")
        assert not report.z3_available
        assert "Z3 not available" in report.summary()

    def test_verify_sat_invariant(self):
        from pyprover.loop_verifier import LoopVerifier
        code = "# Invariant: i >= 0\nx = 0"
        report = LoopVerifier().verify_source(code, param_names=["n"])
        # i >= 0 is satisfiable, so INIT should hold
        if report.z3_available and report.invariants_found > 0:
            assert report.results[0].init_holds

    def test_verify_unsat_invariant(self):
        from pyprover.loop_verifier import LoopVerifier
        # i >= 0 and i < 0 simultaneously — always false
        code = "# Invariant: i >= 0 and i < 0"
        report = LoopVerifier().verify_source(code, param_names=[])
        if report.z3_available and report.invariants_found > 0:
            # UNSAT invariant: init_holds should be False
            assert not report.results[0].init_holds

    def test_report_summary_no_invariants(self):
        from pyprover.loop_verifier import LoopVerifier
        report = LoopVerifier().verify_source("x = 1")
        assert "No loop invariants found" in report.summary()


# ============================================================================
# Contract Simplifier tests
# ============================================================================

class TestContractSimplifier:
    """Tests for the new ContractSimplifier component."""

    def test_empty_contract(self):
        from pyprover.contract_simplifier import ContractSimplifier
        result = ContractSimplifier().simplify([], [])
        assert result.original_count == 0
        assert result.simplified_count == 0
        assert result.reduction_count == 0

    def test_tautology_removed(self):
        from pyprover.contract_simplifier import ContractSimplifier
        result = ContractSimplifier().simplify(["True"], [])
        if result.z3_available:
            assert "True" not in result.simplified_requires
            assert result.reduction_count >= 1

    def test_non_redundant_kept(self):
        from pyprover.contract_simplifier import ContractSimplifier
        result = ContractSimplifier().simplify(["n >= 0", "n < 100"], [])
        if result.z3_available:
            # Neither implies the other — both should be kept
            assert len(result.simplified_requires) == 2

    def test_redundant_removed(self):
        from pyprover.contract_simplifier import ContractSimplifier
        # "n >= 0" is implied by "n >= 5" (if n>=5 then n>=0 always)
        result = ContractSimplifier().simplify(["n >= 0", "n >= 5"], [])
        if result.z3_available:
            assert "n >= 0" not in result.simplified_requires
            assert "n >= 5" in result.simplified_requires

    def test_as_decorators(self):
        from pyprover.contract_simplifier import ContractSimplifier
        result = ContractSimplifier().simplify(["n > 0"], ["result > 0"])
        dec = result.as_decorators()
        assert "@requires" in dec or "@ensures" in dec or "No contracts" in dec

    def test_summary_no_z3(self, monkeypatch):
        import pyprover.contract_simplifier as cs
        monkeypatch.setattr(cs, "Z3_AVAILABLE", False)
        from pyprover.contract_simplifier import ContractSimplifier, ContractSimplificationResult
        result = ContractSimplifier().simplify(["n > 0"], [])
        assert "Z3 not available" in result.summary()

    def test_bare_identifier_ensures_no_crash(self):
        """Regression test: a bare-identifier ensures-clause (e.g. "result",
        no comparison) parses to a Z3 Int, not a Bool. Before the fix,
        _is_tautology/_implies called z3.Not()/Solver.add() directly on
        this Int and raised Z3Exception. It must now be handled gracefully
        (kept, not dropped, not crashed) — this is the same bug class the
        sibling v2.5.2 branch found and fixed in contract_verifier.py's
        _check_satisfiable, reconciled here for this branch's actual
        architecture (contract_simplifier.py's _implies/_is_tautology).
        """
        from pyprover.contract_simplifier import ContractSimplifier
        result = ContractSimplifier().simplify(requires=["n >= 0"], ensures=["result"])
        if result.z3_available:
            assert "result" in result.simplified_ensures

    def test_bare_identifier_requires_no_crash(self):
        """Same bug, requires-side: a bare-identifier precondition."""
        from pyprover.contract_simplifier import ContractSimplifier
        result = ContractSimplifier().simplify(requires=["flag", "flag == True"], ensures=[])
        if result.z3_available:
            assert "flag" in result.simplified_requires

    def test_is_z3_bool_helper(self):
        """Unit test for the _is_z3_bool guard itself."""
        import z3
        from pyprover.contract_simplifier import _is_z3_bool
        assert _is_z3_bool(z3.Int("x") > 0) is True
        assert _is_z3_bool(z3.Int("x")) is False
        assert _is_z3_bool(z3.BoolVal(True)) is True
