"""Phase 5 of MasterDebugger (regression test generation) must not fail silently.

Before the fix, any exception from the test generator was swallowed with
`except Exception: pass`, so a report with issues and an empty test_suite was
indistinguishable from a run where no tests were needed.
"""

import asyncio

import pytest

import src.test_generator.test_generator as test_generator_module
from src.master_debugger.orchestrator import MasterDebugger

BUGGY_CODE = "def f(x):\n    return undefined_name_xyz + x\n"


def _run(code):
    return asyncio.run(
        MasterDebugger(use_pyprover=False).debug_comprehensive(
            code, "python", phases=["static", "runtime"]
        )
    )


def test_phase5_failure_is_recorded_and_reported(monkeypatch, capsys):
    def failing_generator(*args, **kwargs):
        raise RuntimeError("simulated generator failure")

    monkeypatch.setattr(test_generator_module, "generate_tests", failing_generator)

    report = _run(BUGGY_CODE)

    assert report.issues_found, "precondition: the buggy code must produce issues"
    assert report.test_suite == ""
    assert report.test_generation_error == "RuntimeError: simulated generator failure"
    assert "Phase 5 test generation failed" in capsys.readouterr().err


def test_phase5_success_fills_test_suite_and_leaves_no_error():
    report = _run(BUGGY_CODE)

    assert report.issues_found, "precondition: the buggy code must produce issues"
    assert report.test_suite
    assert report.test_generation_error is None


def test_clean_code_skips_phase5_entirely(monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("phase 5 should not run when no issues were found")

    monkeypatch.setattr(test_generator_module, "generate_tests", must_not_run)

    report = _run("def f(x: int) -> int:\n    return x + 1\n")

    assert not report.issues_found, "precondition: clean code must produce no issues"
    assert report.test_suite == ""
    assert report.test_generation_error is None
