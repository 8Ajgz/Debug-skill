"""Batch contract verification across many functions at once.

Restores parallel_verifier.py from PyProver v13.0 (roadmap section 2.1), rebuilt on
ContractVerifier. Z3 keeps global state, so the work runs in worker processes,
not threads: each process has its own Z3 context. Results are cached in the
parent process (see verification_cache), so repeated functions are not
re-solved.
"""
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .contract_verifier import ContractVerifier
from .verification_cache import cache_key, get_cached, store


def _verify_in_worker(code: str) -> Dict[str, Any]:
    """Module-level so it can be pickled for the process pool."""
    try:
        return ContractVerifier.verify_contract(code)
    except Exception as e:  # keep one bad input from failing the whole batch
        return {
            "verified": False,
            "preconditions_ok": False,
            "postconditions_ok": False,
            "details": [f"error during verification: {type(e).__name__}: {e}"],
        }


def batch_verify(
    sources: Mapping[str, str],
    max_workers: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """Verify each source and return a result per name, in input order.

    Args:
        sources: mapping of a name (usually the function name) to its source text.
        max_workers: worker process count. None uses the CPU count, capped at the
            number of uncached sources. 1 runs everything in this process.

    Returns:
        Dict with the same keys as sources, each value a ContractVerifier result.
    """
    results: Dict[str, Dict[str, Any]] = {}
    pending: List[Tuple[str, str, str]] = []  # (name, code, cache key)

    for name, code in sources.items():
        key = cache_key(code)
        hit = get_cached(key)
        if hit is not None:
            results[name] = hit
        else:
            pending.append((name, code, key))

    if pending:
        workers = max_workers if max_workers is not None else (os.cpu_count() or 1)
        workers = max(1, min(workers, len(pending)))
        if workers == 1:
            computed = [_verify_in_worker(code) for _, code, _ in pending]
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                computed = list(pool.map(_verify_in_worker, [code for _, code, _ in pending]))
        for (name, _, key), result in zip(pending, computed):
            store(key, result)
            results[name] = result

    return {name: results[name] for name in sources}
