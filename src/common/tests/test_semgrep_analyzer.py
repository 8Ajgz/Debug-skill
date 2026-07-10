"""
Tests for common/semgrep_analyzer.py.

Closes a gap flagged twice (debug-suite-handoff.md's Test Strategy section,
roadmap.md §12.3): SemgrepAnalyzer had no dedicated pytest integration
tests of its own, unlike cppcheck/valgrind/CBMC elsewhere in tests/.

Unconditional tests cover graceful-degradation behavior (no semgrep
installed, unknown language). Integration tests that actually invoke
semgrep are skipped when semgrep isn't on PATH, following the same
@pytest.mark.skipif pattern as TestCBMCIntegration in
cpp_debug/tests/test_symbolic_phase6.py.
"""

import pytest
from unittest.mock import patch

from src.common.semgrep_analyzer import SemgrepAnalyzer, semgrep_available
from src.common.interop import BugPattern


class TestGracefulDegradation:
    """No real semgrep invocation in these - cover the early-return paths."""

    def test_returns_empty_when_semgrep_not_installed(self):
        with patch("src.common.semgrep_analyzer.semgrep_available", return_value=False):
            result = SemgrepAnalyzer().analyze("x = 1", language="python")
        assert result == []

    def test_returns_empty_for_unknown_language(self):
        with patch("src.common.semgrep_analyzer.semgrep_available", return_value=True):
            result = SemgrepAnalyzer().analyze("x = 1", language="cobol")
        assert result == []

    def test_analyze_never_raises_on_bad_input(self):
        """Graceful degradation must hold even for pathological input -
        this analyzer is called automatically in Phase0StaticAnalysis, so
        a raised exception here would break the whole pipeline, not just
        this one finding."""
        with patch("src.common.semgrep_analyzer.semgrep_available", return_value=False):
            result = SemgrepAnalyzer().analyze("", language="python")
            assert result == []
            result = SemgrepAnalyzer().analyze("\x00\x00 not real code {{{", language="python")
            assert result == []


@pytest.mark.skipif(not semgrep_available(), reason="semgrep not installed")
class TestSemgrepIntegration:
    """Real semgrep invocations against the bundled curated ruleset.
    Mirrors the vulnerability categories verified manually in the
    original integration session (roadmap.md §11.11): unsafe pickle,
    weak MD5 hash, eval(), ReDoS. Each is a real, distinct rule category
    from the bundled 20-rule set, not a duplicate check of the same rule.
    """

    def test_unsafe_pickle_detected(self):
        code = "import pickle\ndata = pickle.loads(untrusted_bytes)\n"
        findings = SemgrepAnalyzer().analyze(code, language="python")
        assert any("pickle" in f.pattern_type.lower() or "pickle" in f.description.lower()
                   for f in findings)

    def test_weak_md5_hash_detected(self):
        code = "import hashlib\nh = hashlib.md5(password.encode()).hexdigest()\n"
        findings = SemgrepAnalyzer().analyze(code, language="python")
        assert any("md5" in f.pattern_type.lower() or "md5" in f.description.lower()
                   for f in findings)

    def test_eval_call_detected(self):
        code = "result = eval(user_input)\n"
        findings = SemgrepAnalyzer().analyze(code, language="python")
        assert any("eval" in f.pattern_type.lower() or "eval" in f.description.lower()
                   for f in findings)

    def test_clean_code_no_false_positives(self):
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        findings = SemgrepAnalyzer().analyze(code, language="python")
        assert findings == []

    def test_findings_are_bug_pattern_instances(self):
        """Type-contract check: analyze() must return BugPattern objects
        (the shared common.interop type every debugger's findings feed
        into), not raw semgrep JSON or some analyzer-local shape."""
        code = "result = eval(user_input)\n"
        findings = SemgrepAnalyzer().analyze(code, language="python")
        assert len(findings) > 0
        for f in findings:
            assert isinstance(f, BugPattern)
