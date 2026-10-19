"""Tests for invariant templates: each generated invariant must hold at every iteration
of a reference loop. These are runtime checks on sample data, not formal proofs."""
import random

import pytest

from ..invariant_templates import (
    BinarySearchBounds,
    FilterCount,
    MinMaxLoop,
    Scan,
    StateMachine,
    SumAccumulator,
)

pytestmark = pytest.mark.verification

RNG = random.Random(1234)
SAMPLES = [[RNG.randint(-50, 50) for _ in range(RNG.randint(1, 12))] for _ in range(60)]


def _holds(invariant: str, env: dict) -> bool:
    # Test-only: evaluates generated invariant strings against reference data.
    return bool(eval(invariant, {"len": len, "min": min, "max": max, "sum": sum}, env))


class TestGeneratedStrings:
    def test_binary_search_bounds_text(self):
        assert BinarySearchBounds().generate_invariant() == (
            "lo >= 0 and hi < len(arr) and lo <= hi + 1")

    def test_min_max_rejects_unknown_op(self):
        with pytest.raises(ValueError):
            MinMaxLoop(best_var="best", op="median").generate_invariant()

    def test_state_machine_needs_states(self):
        with pytest.raises(ValueError):
            StateMachine(states=()).generate_invariant()

    def test_state_machine_text(self):
        assert StateMachine(("idle", "run")).generate_invariant() == (
            '(state == "idle" or state == "run")')


class TestInvariantsHoldOnReferenceLoops:
    @pytest.mark.parametrize("arr", SAMPLES)
    def test_min_max(self, arr):
        inv = MinMaxLoop(best_var="best", op="min").generate_invariant()
        best = arr[0]
        for i in range(len(arr)):
            best = min(best, arr[i])
            assert _holds(inv, {"arr": arr, "i": i, "best": best})

    @pytest.mark.parametrize("arr", SAMPLES)
    def test_sum_accumulator(self, arr):
        inv = SumAccumulator(acc_var="total").generate_invariant()
        total = 0
        for i in range(len(arr)):
            assert _holds(inv, {"arr": arr, "i": i, "total": total})
            total += arr[i]
        assert _holds(inv, {"arr": arr, "i": len(arr), "total": total})

    @pytest.mark.parametrize("arr", SAMPLES)
    def test_filter_count(self, arr):
        inv = FilterCount(count_var="count", condition="x > 0").generate_invariant()
        count = 0
        for i in range(len(arr)):
            assert _holds(inv, {"arr": arr, "i": i, "count": count})
            if arr[i] > 0:
                count += 1
        assert _holds(inv, {"arr": arr, "i": len(arr), "count": count})

    @pytest.mark.parametrize("arr", SAMPLES)
    def test_scan(self, arr):
        inv = Scan().generate_invariant()
        result = []
        for i in range(len(arr)):
            assert _holds(inv, {"result": result, "i": i})
            result.append(arr[i] * 2)

    @pytest.mark.parametrize("arr", SAMPLES)
    def test_binary_search_bounds(self, arr):
        arr = sorted(arr)
        inv = BinarySearchBounds().generate_invariant()
        target = arr[len(arr) // 2]
        lo, hi = 0, len(arr) - 1
        while lo <= hi:
            assert _holds(inv, {"arr": arr, "lo": lo, "hi": hi})
            mid = (lo + hi) // 2
            if arr[mid] == target:
                break
            if arr[mid] < target:
                lo = mid + 1
            else:
                hi = mid - 1
        assert _holds(inv, {"arr": arr, "lo": lo, "hi": hi})

    def test_state_machine_membership(self):
        inv = StateMachine(("idle", "run", "done")).generate_invariant()
        for state in ("idle", "run", "done"):
            assert _holds(inv, {"state": state})
        assert not _holds(inv, {"state": "crashed"})
