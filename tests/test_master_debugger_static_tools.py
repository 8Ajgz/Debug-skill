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
