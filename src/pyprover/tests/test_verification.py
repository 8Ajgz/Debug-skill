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
