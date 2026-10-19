"""Static-analysis tool failures must not look like clean code.

Before the fix, bandit's crash or unparseable output and semgrep's exceptions
were swallowed, and bandit/semgrep findings were computed but never reached
the report's issues, so they could not change the verdict.
"""

import asyncio
import json
import os
import stat

import pytest

from src.master_debugger.orchestrator import MasterDebugger
from src.master_debugger.phases import Phase0StaticAnalysis

CODE = "import os\nos.system('ls')\n"


def _fake_bandit(bin_dir, script_body):
    path = bin_dir / "bandit"
    path.write_text("#!/bin/sh\n" + script_body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def fake_bandit_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")
    return tmp_path


def test_bandit_crash_is_recorded_as_tool_error(fake_bandit_dir):
    _fake_bandit(fake_bandit_dir, "echo 'Traceback: bandit crashed'\nexit 2\n")

    result = Phase0StaticAnalysis.run(CODE)

    assert result.bandit_warnings == []
    assert any(e.startswith("bandit: unparseable output") for e in result.tool_errors)


def test_bandit_findings_reach_the_report(fake_bandit_dir):
    payload = {"results": [{
        "test_id": "B605", "issue_severity": "HIGH",
        "issue_text": "Starting a process with a shell", "line_number": 2,
    }]}
    _fake_bandit(fake_bandit_dir, f"echo '{json.dumps(payload)}'\nexit 1\n")

    result = Phase0StaticAnalysis.run(CODE)
    assert result.tool_errors == []
    assert result.bandit_warnings == ["[B605] HIGH: Starting a process with a shell (line 2)"]

    report = asyncio.run(
        MasterDebugger(use_pyprover=False).debug_comprehensive(CODE, "python", phases=["static"])
    )
    bandit_issues = [i for i in report.issues_found if i.type == "bandit_warning"]
    assert len(bandit_issues) == 1
    assert report.overall_health != "✅ VERIFIED"


def test_semgrep_exception_is_recorded_as_tool_error(monkeypatch):
    from src.common import semgrep_analyzer

    def broken_analyze(self, code, language="python"):
        raise RuntimeError("semgrep exploded")

    monkeypatch.setattr(semgrep_analyzer.SemgrepAnalyzer, "analyze", broken_analyze)

    result = Phase0StaticAnalysis.run(CODE)

    assert result.semgrep_findings == []
    assert "semgrep: RuntimeError: semgrep exploded" in result.tool_errors


def test_broken_static_tool_keeps_verdict_out_of_verified(fake_bandit_dir):
    _fake_bandit(fake_bandit_dir, "echo 'not json'\nexit 2\n")

    report = asyncio.run(
        MasterDebugger(use_pyprover=False).debug_comprehensive(
            "def f(x: int) -> int:\n    return x + 1\n", "python", phases=["static"]
        )
    )

    assert any(i.type == "static_tool_error" for i in report.issues_found)
    assert report.overall_health != "✅ VERIFIED"


def _fake_slow_mypy(bin_dir):
    path = bin_dir / "mypy"
    path.write_text("#!/bin/sh\nsleep 7\nexit 1\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_mypy_timeout_is_recorded_not_read_as_clean(fake_bandit_dir):
    _fake_slow_mypy(fake_bandit_dir)

    result = Phase0StaticAnalysis.run("def f(x: int) -> int:\n    return x\n")

    assert result.mypy_errors == []
    assert "mypy: timed out after 5s" in result.tool_errors


def test_mypy_timeout_reaches_the_verdict(fake_bandit_dir):
    _fake_slow_mypy(fake_bandit_dir)

    report = asyncio.run(
        MasterDebugger(use_pyprover=False).debug_comprehensive(
            "def f(x: int) -> int:\n    return x\n", "python", phases=["static"]
        )
    )

    assert any(i.type == "static_tool_error" and "mypy" in i.description for i in report.issues_found)
    assert report.overall_health != "✅ VERIFIED"


def test_v5_timed_out_mypy_is_not_a_passed_phase(fake_bandit_dir):
    from src.master_debugger.orchestrator_v5 import MasterDebuggerV5

    _fake_slow_mypy(fake_bandit_dir)

    report = MasterDebuggerV5().debug("def f(x: int) -> int:\n    return x + 1\n")

    assert report.phase_0_static.passed is False
    assert report.total_issues >= 1
    assert report.confidence_score < 1.0


def test_v5_counts_bandit_findings(fake_bandit_dir):
    from src.master_debugger.orchestrator_v5 import MasterDebuggerV5

    payload = {"results": [{
        "test_id": "B605", "issue_severity": "HIGH",
        "issue_text": "Starting a process with a shell", "line_number": 2,
    }]}
    _fake_bandit(fake_bandit_dir, f"echo '{json.dumps(payload)}'\nexit 1\n")

    report = MasterDebuggerV5().debug(CODE)

    assert report.total_issues >= len(report.phase_0_static.bandit_warnings) == 1


def _broken_tracer(monkeypatch):
    import src.python_debug as python_debug

    def boom(*args, **kwargs):
        raise RuntimeError("tracer broke")

    monkeypatch.setattr(python_debug, "execute_with_debug", boom)


def test_runtime_tracer_failure_is_an_issue(monkeypatch):
    _broken_tracer(monkeypatch)

    report = asyncio.run(
        MasterDebugger(use_pyprover=False).debug_comprehensive(
            "def f(x: int) -> int:\n    return x + 1\n", "python", phases=["runtime"]
        )
    )

    assert any(i.type == "runtime_tool_error" and "tracer broke" in i.description
               for i in report.issues_found)
    assert report.overall_health != "✅ VERIFIED"


def test_v5_runtime_tracer_failure_counts_and_does_not_pass(monkeypatch):
    from src.master_debugger.orchestrator_v5 import MasterDebuggerV5

    _broken_tracer(monkeypatch)

    report = MasterDebuggerV5().debug("def f(x: int) -> int:\n    return x + 1\n")

    assert report.phase_1_runtime.tool_error is not None
    assert report.phase_1_runtime.passed is False
    assert report.total_issues >= 1


def test_traced_program_exception_is_not_a_tool_error():
    from src.master_debugger.phases import Phase1RuntimeDebug

    result = Phase1RuntimeDebug.run("raise ValueError('the program itself fails')\n")

    assert result.tool_error is None


def test_crashed_async_check_does_not_read_as_verified():
    from types import SimpleNamespace
    from src.common.interop import RiskLevel

    class StubBridge:
        def is_available(self):
            return True

        def verify(self, code, language):
            return SimpleNamespace(risk_level=RiskLevel.LOW, confidence_score=0.95, summary="ok")

        def verify_async(self, code, language):
            raise RuntimeError("async verifier crashed")

    md = MasterDebugger(use_pyprover=False)
    md.pyprover_bridge = StubBridge()

    report = asyncio.run(
        md.debug_comprehensive("def f(x: int) -> int:\n    return x + 1\n", "python", phases=["formal"])
    )

    assert any(i.type == "async_tool_error" and "async verifier crashed" in i.description
               for i in report.issues_found)
    assert report.overall_health != "✅ VERIFIED"


def test_crashed_formal_check_is_reported_not_completed():
    from src.master_debugger.orchestrator import DebugPhase

    class CrashingBridge:
        def is_available(self):
            return True

        def verify(self, code, language):
            raise RuntimeError("pyprover crashed")

        def verify_async(self, code, language):
            return None

    md = MasterDebugger(use_pyprover=False)
    md.pyprover_bridge = CrashingBridge()

    report = asyncio.run(
        md.debug_comprehensive("def f(x: int) -> int:\n    return x + 1\n", "python", phases=["formal"])
    )

    assert any(i.type == "formal_tool_error" and "pyprover crashed" in i.description
               for i in report.issues_found)
    assert DebugPhase.FORMAL not in report.phases_completed


def test_crashed_python_phase_is_reported_not_silent(monkeypatch):
    from src.master_debugger import phases

    def boom(code):
        raise RuntimeError("static phase crashed")

    monkeypatch.setattr(phases.Phase0StaticAnalysis, "run", staticmethod(boom))

    report = asyncio.run(
        MasterDebugger(use_pyprover=False).debug_comprehensive(
            "def f(x: int) -> int:\n    return x + 1\n", "python", phases=["static"]
        )
    )

    assert any(i.type == "analysis_error" and "static phase crashed" in i.description
               for i in report.issues_found)
    assert report.overall_health != "✅ VERIFIED"


def test_crashed_design_review_is_reported_as_not_run(monkeypatch):
    from src.troubleshooting import Troubleshooter

    def boom(self, code, context=None):
        raise RuntimeError("troubleshooter crashed")

    monkeypatch.setattr(Troubleshooter, "diagnose", boom)

    report = asyncio.run(
        MasterDebugger(use_pyprover=False).debug_comprehensive(
            "def f(x: int) -> int:\n    return x + 1\n", "python", phases=["testing"]
        )
    )

    errors = [i for i in report.issues_found if i.type == "design_review_error"]
    assert len(errors) == 1
    assert "troubleshooter crashed" in errors[0].description
    assert not any(i.type == "design_review_failed" for i in report.issues_found)
