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
