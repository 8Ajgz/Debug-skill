"""PyProver v14.0 - Formal code verification with Z3 SMT solver"""
try:
    from .contract_verifier import ContractVerifier, verify_contract
    from .async_verifier import async_verifier
    __all__ = ['ContractVerifier', 'verify_contract', 'async_verifier']
except ImportError:
    __all__ = []

__version__ = "14.0"

# Convenience function
def verify_contract(code: str, language: str = "python"):
    """Verify contract using formal methods"""
    verifier = ContractVerifier()
    return verifier.verify_contract(code)
