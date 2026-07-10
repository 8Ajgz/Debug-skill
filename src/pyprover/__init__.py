"""PyProver v14.1 - Formal code verification with Z3 SMT solver"""
try:
    from .contract_verifier import ContractVerifier
    from .async_verifier import AsyncVerifier
    from .ffi_verifier import FFIVerifier
    from .loop_verifier import LoopVerifier, extract_loop_invariants, LoopVerificationReport
    from .contract_simplifier import ContractSimplifier, simplify_parsed_contract, ContractSimplificationResult
    from .equivalence_verifier import (
        verify_expression_equivalence, verify_function_equivalence,
        simplify_function, propose_redundant_branch_removal,
        EquivalenceResult, SimplificationResult, UnsupportedConstructError,
    )
    from .quantifiers import (
        try_parse_quantifier, check_quantifier,
        QuantifierClause, QuantifierCheckResult,
    )
    from .ghost_state import (
        GhostStateTracker, GhostVariable, GhostUpdate, GhostStateResult,
    )
    from .z3_builtins import try_call_to_z3, infer_string_names, seed_string_env

    async_verifier = AsyncVerifier()
    ffi_verifier = FFIVerifier()

    __all__ = [
        'ContractVerifier', 'verify_contract',
        'AsyncVerifier', 'async_verifier',
        'FFIVerifier', 'ffi_verifier',
        'LoopVerifier', 'extract_loop_invariants', 'LoopVerificationReport',
        'ContractSimplifier', 'simplify_parsed_contract', 'ContractSimplificationResult',
        'verify_expression_equivalence', 'verify_function_equivalence',
        'simplify_function', 'propose_redundant_branch_removal',
        'EquivalenceResult', 'SimplificationResult', 'UnsupportedConstructError',
        'try_parse_quantifier', 'check_quantifier',
        'QuantifierClause', 'QuantifierCheckResult',
        'GhostStateTracker', 'GhostVariable', 'GhostUpdate', 'GhostStateResult',
        'try_call_to_z3', 'infer_string_names', 'seed_string_env',
    ]
except ImportError:
    __all__ = []

__version__ = "14.3"

# Convenience functions
def verify_contract(code: str, language: str = "python"):
    """Verify contract using formal methods"""
    verifier = ContractVerifier()
    return verifier.verify_contract(code)

def verify_loop_invariants(code: str, param_names=None):
    """Verify all loop invariants annotated in code. Returns a LoopVerificationReport."""
    return LoopVerifier().verify_source(code, param_names=param_names or [])

def simplify_contract(requires, ensures, timeout_ms=3000):
    """Simplify a contract's requires/ensures lists. Returns ContractSimplificationResult."""
    return simplify_parsed_contract(requires, ensures, timeout_ms=timeout_ms)
