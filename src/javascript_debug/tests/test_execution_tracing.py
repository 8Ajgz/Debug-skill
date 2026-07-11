"""
JavaScript Debug integration tests for verification-debugging-suite

Tests verify that JavaScript debugging can actually be invoked (via a real
Node.js subprocess) and results parsed correctly.

Previously this file's tests were not real checks: several asserted
tautologies (`assert all(field in expected_fields for field in
expected_fields)`, `assert len(expected_patterns) == 10`) that pass
regardless of what the product does, and three were a bare `pass` body
that tests nothing at all. None of them would have caught
`execute_with_debug()`/`analyze_patterns()` being unconditional stubs, or
the two real bugs found in `debug-engine.js` while fixing that stub (see
STUBS.md and CHANGELOG.md [2.9.5]): `instrumentCode()` left every
`logVariable()` call unclosed (100% syntax error on every declaration),
and `logVariable()` had no `return value` (so, even after fixing the
syntax error, every instrumented variable was silently rebound to
`undefined`). Rewritten to actually invoke Node.js and check real output.
"""

import shutil

import pytest

from src.javascript_debug import JavaScriptDebugger

NODE_AVAILABLE = shutil.which("node") is not None
pytestmark = pytest.mark.skipif(not NODE_AVAILABLE, reason="node is not installed")


@pytest.mark.integration
def test_javascript_debugger_import():
    assert JavaScriptDebugger is not None


@pytest.mark.integration
def test_execute_with_debug_runs_simple_code():
    d = JavaScriptDebugger()
    result = d.execute_with_debug("let x = 1 + 2;\nconsole.log(x);")
    assert result["success"] is True
    assert result["report"]["exceptionInfo"] is None


@pytest.mark.integration
def test_execute_with_debug_tracks_variable_value():
    """Regression check for the missing `return value` bug in
    logVariable(): the instrumented variable must hold its real value,
    not undefined."""
    d = JavaScriptDebugger()
    result = d.execute_with_debug("let x = 42;")
    history = result["report"]["variables"]["x"]
    assert history[-1]["value"] == 42


@pytest.mark.integration
def test_execute_with_debug_survives_semicolons_in_strings():
    """Regression check for instrumentCode()'s statement-end scanner:
    a semicolon inside a string literal must not be treated as the end
    of the declaration statement."""
    d = JavaScriptDebugger()
    result = d.execute_with_debug('let s = "a; b; c";')
    assert result["success"] is True
    assert result["report"]["exceptionInfo"] is None
    assert result["report"]["variables"]["s"][-1]["value"] == "a; b; c"


@pytest.mark.integration
def test_execute_with_debug_captures_real_exception():
    d = JavaScriptDebugger()
    result = d.execute_with_debug("let obj = null;\nlet value = obj.property;")
    assert result["success"] is True
    exc = result["report"]["exceptionInfo"]
    assert exc is not None
    assert exc["type"] == "TypeError"


@pytest.mark.integration
def test_analyze_patterns_detects_null_reference():
    """End-to-end: real Node execution must produce a real
    null_reference pattern for a real null-dereference, not an empty
    list (the previous stub's only possible output)."""
    d = JavaScriptDebugger()
    result = d.execute_with_debug("let obj = null;\nlet value = obj.property;")
    patterns = d.analyze_patterns(result)
    assert any(p["patternType"] == "null_reference" for p in patterns)


@pytest.mark.integration
def test_aliasing_is_tracked_across_variables():
    """Regression check: two variables referencing the same array must
    show the same mutated value after one is mutated through the
    other -- only possible if logVariable() actually returns real
    object references, not undefined."""
    d = JavaScriptDebugger()
    code = "let x = [1, 2, 3];\nlet y = x;\ny.push(4);"
    result = d.execute_with_debug(code)
    x_final = result["report"]["variables"]["x"][-1]["value"]
    y_final = result["report"]["variables"]["y"][-1]["value"]
    assert x_final == [1, 2, 3, 4]
    assert y_final == [1, 2, 3, 4]


@pytest.mark.integration
def test_execute_with_debug_reports_unavailable_honestly_when_node_missing(monkeypatch):
    d = JavaScriptDebugger()
    monkeypatch.setattr(d, "node_available", False)
    result = d.execute_with_debug("let x = 1;")
    assert result["success"] is False
    assert "not installed" in result["error"]


@pytest.mark.integration
def test_analyze_patterns_returns_empty_for_report_without_patterns():
    d = JavaScriptDebugger()
    assert d.analyze_patterns({"report": {}}) == []
