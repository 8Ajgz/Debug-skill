"""PyProver v14.0 - Formal code verification with Z3 SMT solver"""
try:
    from .contract_verifier import ContractVerifier
    from .async_verifier import AsyncVerifier
    from .ffi_verifier import FFIVerifier

    # Module-level singletons for convenience access (e.g. `pyprover.async_verifier`).
    # NOTE: previous versions tried `from .async_verifier import async_verifier`,
    # but async_verifier.py only defines the AsyncVerifier class, not an instance -
    # that import always raised ImportError and silently emptied __all__.
    async_verifier = AsyncVerifier()
    ffi_verifier = FFIVerifier()

    __all__ = [
        'ContractVerifier', 'verify_contract',
        'AsyncVerifier', 'async_verifier',
        'FFIVerifier', 'ffi_verifier',
    ]
except ImportError:
    __all__ = []

__version__ = "14.0"

# Convenience function
def verify_contract(code: str, language: str = "python"):
    """Verify contract using formal methods"""
    verifier = ContractVerifier()
    return verifier.verify_contract(code)
