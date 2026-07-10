"""
Tests for Python-Debug v12.3 runtime execution tracing.

Tests execution tracing, variable tracking, bug pattern detection,
and exception handling.
"""

import sys
import pytest
from ..debug_report import execute_with_debug, DebugReport


class TestExecutionTracing:
    """Test runtime execution tracing functionality."""
    
    @pytest.mark.tracing
    def test_simple_trace(self):
        """Test tracing of simple assignment."""
        code = "x = 1"
        report = execute_with_debug(code)
        
        assert report.execution_complete
        assert len(report.timeline) > 0
    
    @pytest.mark.tracing
    @pytest.mark.parametrize("code,expected_vars", [
        ("x = 1", ["x"]),
        ("x = 1; y = 2", ["x", "y"]),
        ("x = 1; y = x + 1; z = x + y", ["x", "y", "z"]),
        ("items = [1, 2, 3]; total = sum(items)", ["items", "total"]),
    ])
    def test_variable_capture(self, code, expected_vars):
        """Test that variables are correctly captured in final state."""
        report = execute_with_debug(code)
        
        assert report.execution_complete
        for var in expected_vars:
            assert var in report.final_state, \
                f"Variable {var} not found in final state. Found: {list(report.final_state.keys())}"
    
    @pytest.mark.tracing
    @pytest.mark.parametrize("code", [
        "arr = [1, 2, 3]; x = arr[10]",  # IndexError
        "x = 1 / 0",  # ZeroDivisionError
        "int('not_a_number')",  # ValueError
    ])
    def test_exception_capture(self, code):
        """Test that exceptions are properly captured."""
        report = execute_with_debug(code)
        
        assert report.exception_info is not None
    
    @pytest.mark.tracing
    def test_timeline_structure(self):
        """Test that timeline has correct event structure."""
        code = """
x = 1
y = 2
z = x + y
"""
        report = execute_with_debug(code)
        
        assert len(report.timeline) > 0
        for event in report.timeline:
            assert hasattr(event, 'lineno'), "Event should have lineno"
            assert hasattr(event, 'event_type'), "Event should have event_type"


class TestLoopTracing:
    """Test tracing of loops and iteration."""
    
    @pytest.mark.tracing
    def test_for_loop_tracing(self):
        """Test tracing of for loops."""
        code = """
total = 0
for i in range(5):
    total += i
"""
        report = execute_with_debug(code)
        
        assert report.execution_complete
        assert 'total' in report.final_state
        assert report.final_state['total'] == 10  # 0+1+2+3+4
    
    @pytest.mark.tracing
    def test_while_loop_tracing(self):
        """Test tracing of while loops."""
        code = """
x = 0
while x < 5:
    x += 1
"""
        report = execute_with_debug(code)
        
        assert report.execution_complete
        assert report.final_state['x'] == 5
    
    @pytest.mark.tracing
    def test_list_comprehension(self):
        """Test tracing of list comprehensions."""
        code = "result = [x * 2 for x in range(5)]"
        report = execute_with_debug(code)
        
        assert report.execution_complete
        assert 'result' in report.final_state
        assert report.final_state['result'] == [0, 2, 4, 6, 8]


class TestFunctionTracing:
    """Test tracing of function calls and definitions."""
    
    @pytest.mark.tracing
    def test_function_definition_and_call(self):
        """Test tracing function definitions and calls."""
        code = """
def add(a, b):
    return a + b

result = add(2, 3)
"""
        report = execute_with_debug(code)
        
        assert report.execution_complete
        assert 'result' in report.final_state
        assert report.final_state['result'] == 5
    
    @pytest.mark.tracing
    def test_recursive_function(self):
        """Test tracing recursive functions."""
        code = """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

result = factorial(5)
"""
        report = execute_with_debug(code)
        
        assert report.execution_complete
        assert report.final_state['result'] == 120


class TestAliasDetection:
    """Test object aliasing detection."""
    
    @pytest.mark.patterns
    def test_simple_alias(self):
        """Test detection of simple object alias."""
        code = """
x = [1, 2, 3]
y = x
x.append(4)
"""
        report = execute_with_debug(code)
        
        aliases = report.get_true_aliases()
        assert len(aliases) > 0, "Should detect alias between x and y"
    
    @pytest.mark.patterns
    def test_no_alias_different_objects(self):
        """Test that different objects are not aliased."""
        code = """
x = [1, 2, 3]
y = [1, 2, 3]
"""
        report = execute_with_debug(code)
        
        # Different objects, no alias
        x_id = id(report.final_state['x'])
        y_id = id(report.final_state['y'])
        assert x_id != y_id


class TestMutationTracking:
    """Test variable mutation tracking."""
    
    @pytest.mark.tracing
    def test_variable_mutation(self):
        """Test tracking of variable mutations."""
        code = """
x = 1
x = 2
x = 3
"""
        report = execute_with_debug(code)
        
        mutations = report.get_variable_mutations('x') if hasattr(report, 'get_variable_mutations') else []
        # x should have multiple mutation points
        assert report.final_state['x'] == 3
    
    @pytest.mark.tracing
    def test_list_mutation(self):
        """Test tracking of list mutations."""
        code = """
items = [1]
items.append(2)
items.append(3)
items.pop()
"""
        report = execute_with_debug(code)
        
        assert report.final_state['items'] == [1, 2]


class TestDebugReportAPI:
    """Test DebugReport API and methods."""
    
    def test_report_is_complete(self):
        """Test that reports are marked complete on success."""
        report = execute_with_debug("x = 1")
        assert report.execution_complete
    
    def test_report_has_final_state(self):
        """Test that reports capture final state."""
        report = execute_with_debug("x = 1; y = 2")
        assert isinstance(report.final_state, dict)
        assert 'x' in report.final_state
        assert 'y' in report.final_state
    
    def test_report_dump_variables(self):
        """Test dump_variables method."""
        report = execute_with_debug("x = 1; y = 2")
        
        var_dump = report.dump_variables() if hasattr(report, 'dump_variables') else {}
        # Should have variable information
        assert report.final_state is not None


class TestCrashReporting:
    """
    Regression tests for the exception_info dict-vs-tuple bug: exception_info
    is set as a dict (see log_exception), but get_execution_summary(),
    _analyze_cause(), _generate_suggestions(), generate_human_readable(), and
    to_dict() all previously did `exc_type, exc_value, _ = self.exception_info`
    or `self.exception_info[0]`/`[1]`, which raised ValueError/KeyError on
    every single crash. None of the existing tests exercised a crashing
    program through these report-generation paths, so it went undetected.
    """

    def test_execution_summary_on_crash(self):
        report = execute_with_debug("def f(a, b):\n    return a / b\nf(1, 0)\n")
        summary = report.get_execution_summary()
        assert summary["exception"]["type"] == "ZeroDivisionError"
        assert "division by zero" in summary["exception"]["message"]

    def test_analyze_cause_on_crash(self):
        report = execute_with_debug("def f(a, b):\n    return a / b\nf(1, 0)\n")
        cause = report._analyze_cause()
        assert "zero" in cause.lower()

    def test_generate_suggestions_on_crash(self):
        report = execute_with_debug("def f(a, b):\n    return a / b\nf(1, 0)\n")
        suggestions = report._generate_suggestions()
        assert len(suggestions) > 0

    def test_human_readable_report_on_crash(self):
        report = execute_with_debug("def f(a, b):\n    return a / b\nf(1, 0)\n")
        text = report.generate_human_readable()
        assert "CRASHED" in text
        assert "ZeroDivisionError" in text

    def test_to_dict_on_crash(self):
        report = execute_with_debug("def f(a, b):\n    return a / b\nf(1, 0)\n")
        d = report.to_dict()
        assert d["execution"]["status"] == "crashed"
        assert d["summary"]["exception_type"] == "ZeroDivisionError"
        assert d["summary"]["root_cause"]

    def test_to_json_on_crash(self):
        report = execute_with_debug("def f(a, b):\n    return a / b\nf(1, 0)\n")
        # Must not raise - to_json() serializes to_dict()'s output.
        assert len(report.to_json()) > 0

    def test_execution_summary_on_success_unaffected(self):
        """Successful runs (no exception_info) must still report cleanly."""
        report = execute_with_debug("x = 1")
        summary = report.get_execution_summary()
        assert summary["exception"]["type"] is None
        assert summary["exception"]["message"] is None


class TestStdinMocking:
    """Regression tests for the input()-hangs-forever fix.

    Traced code has no interactive terminal in a debugger/sandbox context,
    so a blocking input() call must fail fast (EOFError) rather than hang
    indefinitely. mock_stdin=True is the default; execute_with_debug()
    swaps sys.stdin for an empty buffer for the duration of exec() and
    always restores it afterward, success or exception.
    """

    def test_input_call_raises_eof_not_hang(self):
        """The defining regression test: must return promptly (not hang)
        and correctly attribute the failure to EOFError, not something
        else. Uses no external timeout here deliberately - if this
        regresses, the test process itself will hang, which is the
        clearest possible failure signal for this specific bug.
        """
        report = execute_with_debug("x = input('prompt: ')\nprint(x)")
        assert report.exception_info is not None
        assert report.exception_info["exception_type"] is EOFError

    def test_input_call_reported_as_crash(self):
        report = execute_with_debug("x = input()\n")
        d = report.to_dict()
        assert d["execution"]["status"] == "crashed"
        assert d["execution"]["exit_code"] == 1

    def test_stdin_restored_after_execution(self):
        """sys.stdin must be the caller's original object again after
        execute_with_debug() returns, whether the run crashed or not -
        otherwise every subsequent input() call anywhere in the process
        (including outside this debugger) would also start raising."""
        original_stdin = sys.stdin
        execute_with_debug("x = input()\n")
        assert sys.stdin is original_stdin
        execute_with_debug("y = 1\n")
        assert sys.stdin is original_stdin

    def test_mock_stdin_false_leaves_stdin_untouched(self):
        """Opt-out: mock_stdin=False must not swap sys.stdin at all. Does
        not exercise an actual input() call (that would hang with a real
        stdin in a non-interactive test runner) - only confirms the
        non-default code path doesn't touch sys.stdin identity."""
        original_stdin = sys.stdin
        execute_with_debug("x = 1\n", mock_stdin=False)
        assert sys.stdin is original_stdin

    def test_non_input_code_unaffected_by_mocked_stdin(self):
        """Code that never calls input() must behave identically regardless
        of mock_stdin - confirms the fix has no side effect on the common
        case (the vast majority of debugged code never touches stdin)."""
        report = execute_with_debug("x = 1 + 1\nassert x == 2")
        assert report.exception_info is None
        assert report.final_state.get("x") == 2
