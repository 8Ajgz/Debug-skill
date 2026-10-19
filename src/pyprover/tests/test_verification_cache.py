"""Tests for the SHA256 verification cache and parallel batch verification."""
import pytest

from ..contract_verifier import ContractSpec, ContractVerifier
from .. import verification_cache as vc
from ..parallel_verifier import _verify_in_worker, batch_verify

PROVABLE = "# Pre: x > 100\n# Post: x > 0\ndef f(x):\n    return x\n"
NOT_IMPLIED = "# Pre: x > 0\n# Post: x < 0\ndef g(x):\n    return x\n"
CONTRADICTORY = "# Pre: x > 5\n# Pre: x < 0\ndef h(x):\n    return x\n"


@pytest.fixture(autouse=True)
def _fresh_cache():
    vc.clear_cache()
    yield
    vc.clear_cache()


@pytest.mark.verification
class TestCacheKey:
    def test_same_code_same_key(self):
        assert vc.cache_key(PROVABLE) == vc.cache_key(PROVABLE)

    def test_different_code_different_key(self):
        assert vc.cache_key(PROVABLE) != vc.cache_key(NOT_IMPLIED)

    def test_contract_changes_key(self):
        base = ContractSpec(preconditions=["x > 0"], postconditions=[], invariants=[])
        other = ContractSpec(preconditions=["x > 1"], postconditions=[], invariants=[])
        assert vc.cache_key(PROVABLE, base) != vc.cache_key(PROVABLE, other)

    def test_key_is_sha256_hex(self):
        key = vc.cache_key(PROVABLE)
        assert len(key) == 64
        int(key, 16)


@pytest.mark.verification
class TestVerifyContractCached:
    def test_matches_direct_verification(self):
        cached = vc.verify_contract_cached(NOT_IMPLIED)
        direct = ContractVerifier.verify_contract(NOT_IMPLIED)
        assert cached["verified"] == direct["verified"] is False

    def test_second_call_is_served_from_cache(self):
        vc.verify_contract_cached(PROVABLE)
        assert vc.get_cached(vc.cache_key(PROVABLE)) is not None

    def test_returned_result_is_a_copy(self):
        first = vc.verify_contract_cached(PROVABLE)
        first["verified"] = "tampered"
        second = vc.verify_contract_cached(PROVABLE)
        assert second["verified"] is True

    def test_cache_is_bounded_lru(self, monkeypatch):
        monkeypatch.setattr(vc, "MAX_CACHE_ENTRIES", 3)
        for n in range(5):
            vc.store(f"key-{n}", {"verified": True})
        assert len(vc._cache) == 3
        assert vc.get_cached("key-0") is None
        assert vc.get_cached("key-4") is not None


@pytest.mark.verification
class TestBatchVerify:
    SOURCES = {"f": PROVABLE, "g": NOT_IMPLIED, "h": CONTRADICTORY}

    def test_results_match_sequential_verification(self):
        results = batch_verify(self.SOURCES, max_workers=2)
        for name, code in self.SOURCES.items():
            assert results[name]["verified"] == ContractVerifier.verify_contract(code)["verified"]

    def test_keys_keep_input_order(self):
        results = batch_verify(self.SOURCES, max_workers=2)
        assert list(results) == ["f", "g", "h"]

    def test_single_worker_runs_in_process(self):
        results = batch_verify(self.SOURCES, max_workers=1)
        assert results["f"]["verified"] is True
        assert results["g"]["verified"] is False
        assert results["h"]["verified"] is False

    def test_batch_populates_cache(self):
        batch_verify({"f": PROVABLE}, max_workers=1)
        assert vc.get_cached(vc.cache_key(PROVABLE)) is not None

    def test_empty_batch(self):
        assert batch_verify({}) == {}


@pytest.mark.verification
def test_worker_error_is_reported_not_raised():
    result = _verify_in_worker(None)
    assert result["verified"] is False
    assert any("error during verification" in d for d in result["details"])
