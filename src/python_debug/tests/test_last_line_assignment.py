"""Variables assigned on the last line: the tracer fires before a line runs, so the
last line has no state snapshot. Mutation and alias queries must still work."""
import pytest

from ..debug_report import execute_with_debug

pytestmark = pytest.mark.tracing


def test_mutations_for_last_line_variable_do_not_crash():
    report = execute_with_debug('x = 1\ny = x + 1\nz = y * 2\n')
    mutations = report.get_variable_mutations('z')
    assert mutations, "last-line assignment should be recorded"
    assert mutations == [(3, None, 4)]


def test_final_state_includes_last_line_variable():
    report = execute_with_debug('x = 1\ny = x + 1\nz = y * 2\n')
    assert report.final_state_raw.get('z') == 4
