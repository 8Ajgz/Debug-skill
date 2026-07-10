"""
Tests for the UNHANDLED_EXCEPTION fallback in bug_patterns.py.

Real bug found by direct testing (see roadmap.md §20): BugPatternDetector's
exception-driven dispatch only recognized IndexError/KeyError/TypeError/
ZeroDivisionError. Any other unhandled exception -- confirmed with a bare
undefined-name reference raising NameError -- produced zero patterns despite
report.exception_info correctly capturing a real crash, so
Phase1RuntimeDebug.run()'s `passed = len(patterns) == 0` reported `passed=True`
for code that crashes on every call.
"""

import pytest
from ..debug_report import execute_with_debug
from ..bug_patterns import BugPatternDetector, BugPatternType


class TestUnhandledExceptionFallback:

    def test_name_error_now_detected(self):
        code = """
def f():
    undefined_name_xyz
    return 1

f()
"""
        report = execute_with_debug(code)
        assert report.exception_info is not None  # sanity: the crash was captured
        patterns = BugPatternDetector(report).analyze()
        assert any(p.pattern_type == BugPatternType.UNHANDLED_EXCEPTION for p in patterns)

    def test_attribute_error_now_detected(self):
        code = """
def f(x):
    return x.nonexistent_attribute

f(42)
"""
        report = execute_with_debug(code)
        patterns = BugPatternDetector(report).analyze()
        assert any(p.pattern_type == BugPatternType.UNHANDLED_EXCEPTION for p in patterns)

    def test_pattern_description_names_real_exception(self):
        code = """
def f():
    raise ValueError("custom message here")

f()
"""
        report = execute_with_debug(code)
        patterns = BugPatternDetector(report).analyze()
        unhandled = [p for p in patterns if p.pattern_type == BugPatternType.UNHANDLED_EXCEPTION]
        assert len(unhandled) == 1
        assert "ValueError" in unhandled[0].description
        assert "custom message here" in unhandled[0].description

    def test_specialized_detectors_still_take_priority(self):
        """IndexError must still go through _detect_off_by_one, not the
        generic fallback -- the fallback is an else branch, not a
        replacement for the specialized detectors."""
        code = """
def f():
    arr = [1, 2, 3]
    for i in range(1, len(arr) + 1):
        x = arr[i]
    return x

f()
"""
        report = execute_with_debug(code)
        patterns = BugPatternDetector(report).analyze()
        assert any(p.pattern_type == BugPatternType.OFF_BY_ONE for p in patterns)
        assert not any(p.pattern_type == BugPatternType.UNHANDLED_EXCEPTION for p in patterns)

    def test_no_exception_no_pattern(self):
        code = "x = 1 + 1\n"
        report = execute_with_debug(code)
        patterns = BugPatternDetector(report).analyze()
        assert not any(p.pattern_type == BugPatternType.UNHANDLED_EXCEPTION for p in patterns)

    def test_phase1_passed_is_false_for_unhandled_exception(self):
        """End-to-end: the whole point of this fix. Phase1RuntimeDebug.run()
        must report passed=False when execution crashed with any exception,
        not just the four specialized ones."""
        from ..bug_patterns import BugPatternDetector as _BPD  # local import parity check
        code = """
def f():
    undefined_name_xyz
    return 1

f()
"""
        report = execute_with_debug(code)
        patterns = BugPatternDetector(report).analyze()
        passed = len(patterns) == 0  # mirrors Phase1RuntimeDebug.run()'s own logic
        assert passed is False
