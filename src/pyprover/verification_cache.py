"""SHA256-keyed cache for ContractVerifier results.

Restores the result caching described in roadmap section 2.1 (PyProver v13.0).
Identical code and contract clauses are verified once; later calls return a
copy of the stored result. The cache is per-process and bounded (LRU).
"""
import copy
import hashlib
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

from .contract_verifier import ContractSpec, ContractVerifier

MAX_CACHE_ENTRIES = 256

_lock = threading.Lock()
_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()


def cache_key(code: str, contract: Optional[ContractSpec] = None) -> str:
    """Return the SHA256 hex digest identifying a (code, contract) pair."""
    digest = hashlib.sha256()
    digest.update(code.encode("utf-8", errors="replace"))
    if contract is not None:
        digest.update(repr((
            contract.preconditions,
            contract.postconditions,
            contract.invariants,
        )).encode("utf-8"))
    return digest.hexdigest()


def get_cached(key: str) -> Optional[Dict[str, Any]]:
    """Return a copy of the cached result for key, or None on a miss."""
    with _lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        _cache.move_to_end(key)
        return copy.deepcopy(hit)


def store(key: str, result: Dict[str, Any]) -> None:
    """Store a copy of result under key, evicting the least recently used entry."""
    with _lock:
        _cache[key] = copy.deepcopy(result)
        _cache.move_to_end(key)
        while len(_cache) > MAX_CACHE_ENTRIES:
            _cache.popitem(last=False)


def clear_cache() -> None:
    """Empty the cache."""
    with _lock:
        _cache.clear()


def verify_contract_cached(code: str, contract: Optional[ContractSpec] = None) -> Dict[str, Any]:
    """Run ContractVerifier.verify_contract, reusing a previous result when possible."""
    key = cache_key(code, contract)
    hit = get_cached(key)
    if hit is not None:
        return hit
    result = ContractVerifier.verify_contract(code, contract)
    store(key, result)
    return result
