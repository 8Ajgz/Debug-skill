"""
Tests for the stub fixes documented in STUBS.md:

- run_tests()/measure_coverage(): previously always returned hardcoded
  zeros regardless of input; now execute real pytest/coverage.py (and
  Jest, where available).
- run_fuzzing(): previously returned a hardcoded coverage_estimate of
  0.75 regardless of input; now measures real coverage when test code
  is supplied, or reports None (not a fabricated number) otherwise.
- generate_metamorphic_tests(): previously emitted inputs={} for every
  single metamorphic relation, which always fell through to a bare
  `pass`/`TODO` test body; now generates concrete typed inputs and a
  real assertion per relation.
- _format_value(): previously always emitted Python literals (None/
  True/False) even for Jest output, which is invalid JavaScript.

These tests actually invoke pytest/coverage.py as subprocesses (this
suite's own convention — real tool execution, not mocked), so they are
somewhat slower than a typical unit test; that's intentional here since
the entire point of the fix is that the tools really run.
"""

import shutil

import pytest

from ..test_generator import (
    TestCase,
    _format_value,
    format_tests,
    generate_metamorphic_tests,
    measure_coverage,
    run_fuzzing,
    run_tests,
)

PYTEST_AVAILABLE = shutil.which("pytest") is not None
COVERAGE_AVAILABLE = shutil.which("coverage") is not None


class TestFormatValueLanguageAware:
    """_format_value used to always emit Python literals regardless of
    target language, producing invalid JS for None/bool values."""

    def test_python_none_and_bool(self):
        assert _format_value(None) == "None"
        assert _format_value(True) == "True"
        assert _format_value(False) == "False"

    def test_javascript_none_and_bool(self):
        assert _format_value(None, "javascript") == "null"
        assert _format_value(True, "javascript") == "true"
        assert _format_value(False, "javascript") == "false"

    def test_javascript_nested_list_with_bool(self):
        assert _format_value([True, None], "javascript") == "[true, null]"


class TestMetamorphicRealAssertions:
    """generate_metamorphic_tests() must produce concrete inputs and a
    relation tag, not the previous inputs={} placeholder."""

    def test_symmetry_has_concrete_inputs_and_relation(self):
        metadata = {"name": "distance", "docstring": "", "params": [
            {"name": "p1", "type": "int"}, {"name": "p2", "type": "int"},
        ]}
        tests, report = generate_metamorphic_tests(metadata)
        symmetry = next(t for t in tests if t.relation == "symmetry")
        assert symmetry.inputs  # not empty
        assert "symmetry" in report["patterns"]

    def test_every_matched_pattern_has_nonempty_inputs(self):
        """Regression check for the STUBS.md finding: this used to be
        true for zero patterns; now it must hold for all of them."""
        metadata = {
            "name": "sort_and_distance_and_sum",
            "docstring": "sort, distance, sum, associative, idempotent, monotonic, "
                         "encode, triangle inequality, permutation preserve",
            "params": [{"name": "a", "type": "list"}, {"name": "b", "type": "list"}],
        }
        tests, report = generate_metamorphic_tests(metadata)
        assert len(tests) >= 5
        for t in tests:
            if t.relation not in ("inverse", "generic"):
                assert t.inputs, f"{t.relation} got empty inputs"

    def test_no_pattern_matched_falls_back_to_generic(self):
        metadata = {"name": "frobnicate", "docstring": "", "params": []}
        tests, report = generate_metamorphic_tests(metadata)
        assert report["patterns"] == ["generic"]
        assert tests[0].relation == "generic"

    def test_pytest_body_for_symmetry_is_real_assertion(self):
        metadata = {"name": "manhattan", "docstring": "distance", "params": [
            {"name": "p1", "type": "int"}, {"name": "p2", "type": "int"},
        ]}
        tests, _ = generate_metamorphic_tests(metadata)
        code = format_tests(tests, "python", [], func_name="manhattan")
        assert "TODO: Implement test" not in code
        assert "pass" not in code
        assert "manhattan(" in code
        assert "==" in code or "<=" in code

    @pytest.mark.skipif(not PYTEST_AVAILABLE, reason="pytest not installed")
    def test_symmetry_assertion_actually_passes_for_symmetric_function(self):
        metadata = {"name": "manhattan_distance", "docstring": "distance", "params": [
            {"name": "p1", "type": "int"}, {"name": "p2", "type": "int"},
        ]}
        tests, _ = generate_metamorphic_tests(metadata)
        test_code = format_tests(tests, "python", [], func_name="manhattan_distance")
        source = "def manhattan_distance(p1, p2):\n    return abs(p1 - p2)\n"
        result = run_tests(test_code, "python", source_code=source)
        assert result["tool_available"] is True
        assert result["failed"] == 0
        assert result["passed"] >= 1

    @pytest.mark.skipif(not PYTEST_AVAILABLE, reason="pytest not installed")
    def test_symmetry_assertion_actually_fails_for_asymmetric_function(self):
        metadata = {"name": "bad_distance", "docstring": "distance", "params": [
            {"name": "p1", "type": "int"}, {"name": "p2", "type": "int"},
        ]}
        tests, _ = generate_metamorphic_tests(metadata)
        test_code = format_tests(tests, "python", [], func_name="bad_distance")
        source = "def bad_distance(p1, p2):\n    return p1 - p2\n"  # not symmetric
        result = run_tests(test_code, "python", source_code=source)
        assert result["tool_available"] is True
        assert result["failed"] >= 1


class TestRunTestsReal:
    """run_tests() used to always return {"passed": 0, "failed": 0}
    regardless of whether the tests would actually pass."""

    @pytest.mark.skipif(not PYTEST_AVAILABLE, reason="pytest not installed")
    def test_passing_and_failing_tests_are_distinguished(self):
        source = "def add(a, b):\n    return a + b\n"
        tests = (
            "def test_add_ok():\n    assert add(2, 3) == 5\n\n"
            "def test_add_bad():\n    assert add(2, 2) == 999\n"
        )
        result = run_tests(tests, "python", source_code=source)
        assert result["tool_available"] is True
        assert result["passed"] == 1
        assert result["failed"] == 1

    def test_reports_unavailable_honestly_when_tool_missing(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: None)
        import subprocess as _subprocess

        def _raise(*a, **k):
            raise FileNotFoundError()
        monkeypatch.setattr(_subprocess, "run", _raise)
        from .. import test_generator as tg
        result = tg._run_pytest("def test_x():\n    assert True\n")
        assert result["tool_available"] is False
        assert "not installed" in result["message"]


class TestMeasureCoverageReal:
    """measure_coverage() used to always return {"line_coverage": 0.0,
    "branch_coverage": 0.0} regardless of input."""

    @pytest.mark.skipif(not COVERAGE_AVAILABLE, reason="coverage.py not installed")
    def test_full_coverage_reports_100_percent(self):
        source = "def add(a, b):\n    return a + b\n"
        tests = "def test_add():\n    assert add(2, 3) == 5\n"
        result = measure_coverage(source, tests, "python")
        assert result["tool_available"] is True
        assert result["line_coverage"] == 1.0

    @pytest.mark.skipif(not COVERAGE_AVAILABLE, reason="coverage.py not installed")
    def test_partial_branch_coverage_is_less_than_one(self):
        source = (
            "def classify(x):\n"
            "    if x > 0:\n"
            "        return 1\n"
            "    else:\n"
            "        return 0\n"
        )
        tests = "def test_pos():\n    assert classify(5) == 1\n"  # never hits else
        result = measure_coverage(source, tests, "python")
        assert result["tool_available"] is True
        assert result["branch_coverage"] < 1.0
        assert result["missing_lines"]  # real list of line numbers, not a count


class TestRunFuzzingRealCoverageEstimate:
    """run_fuzzing() used to always return coverage_estimate: 0.75
    regardless of input."""

    def test_no_existing_tests_gives_honest_none_not_075(self):
        code = "def f(x):\n    if x > 0:\n        return 1\n    return 0\n"
        _, report = run_fuzzing(code, "python")
        assert report["coverage_estimate"] is None
        assert report["coverage_estimate"] != 0.75

    @pytest.mark.skipif(not COVERAGE_AVAILABLE or not PYTEST_AVAILABLE,
                        reason="coverage.py/pytest not installed")
    def test_with_existing_tests_gives_real_measured_value(self):
        code = (
            "def classify(x):\n"
            "    if x > 0:\n"
            "        return 1\n"
            "    else:\n"
            "        return 0\n"
        )
        existing_tests = "def test_pos():\n    assert classify(5) == 1\n"
        _, report = run_fuzzing(code, "python", existing_test_code=existing_tests)
        assert report["coverage_estimate"] is not None
        assert 0.0 <= report["coverage_estimate"] <= 1.0
        assert "measured" in report["coverage_estimate_source"]
        # The if-construct with an untested else-branch should show up
        # as a real uncovered condition (reported at its header line).
        assert any(c["line"] == 2 for c in report["uncovered_conditions"])
