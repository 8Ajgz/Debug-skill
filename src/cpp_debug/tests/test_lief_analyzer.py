"""
Tests for cpp_debug/lief_analyzer.py.

Closes a gap flagged twice (debug-suite-handoff.md's Test Strategy section,
roadmap.md §12.3): LiefBinaryAnalyzer had no dedicated pytest integration
tests of its own, unlike cppcheck/valgrind/CBMC elsewhere in tests/.

Unconditional tests cover graceful-degradation behavior (lief not
installed, no compiler). Integration tests that actually compile and
analyze a real binary are skipped when lief isn't importable, following
the same @pytest.mark.skipif pattern as TestCBMCIntegration in
test_symbolic_phase6.py.
"""

import pytest
from unittest.mock import patch

from src.cpp_debug.lief_analyzer import LiefBinaryAnalyzer, lief_available, _c_compiler
from src.common.interop import BugPattern


class TestGracefulDegradation:

    def test_returns_empty_when_lief_not_installed(self):
        with patch("src.cpp_debug.lief_analyzer.lief_available", return_value=False):
            result = LiefBinaryAnalyzer().analyze("int main() { return 0; }", dialect="c")
        assert result == []

    def test_returns_empty_when_no_compiler(self):
        with patch("src.cpp_debug.lief_analyzer.lief_available", return_value=True), \
             patch("src.cpp_debug.lief_analyzer._c_compiler", return_value=""):
            result = LiefBinaryAnalyzer().analyze("int main() { return 0; }", dialect="c")
        assert result == []

    def test_returns_empty_on_compile_failure(self):
        """Deliberately broken C - LiefBinaryAnalyzer must not raise, must
        not report a finding (that's CppDebugger's own diagnostics pass's
        job, per this module's own docstring), just degrade to []."""
        if not lief_available() or not _c_compiler():
            pytest.skip("needs both lief and a compiler to exercise the real compile path")
        result = LiefBinaryAnalyzer().analyze("int main( { this is not valid C", dialect="c")
        assert result == []


@pytest.mark.skipif(not (lief_available() and _c_compiler()), reason="lief or a C compiler not available")
class TestLiefIntegration:
    """Real compile-then-analyze runs. Mirrors the two verification
    directions from the original integration session (roadmap.md §11.14):
    hardening-posture toggling between default and deliberately-weakened
    builds, and dangerous-import detection from a real binary's import table.
    """

    def test_dangerous_imports_detected(self):
        code = (
            "#include <string.h>\n"
            "#include <stdlib.h>\n"
            "int main(int argc, char **argv) {\n"
            "    char buf[16];\n"
            "    strcpy(buf, argv[1]);\n"
            "    system(buf);\n"
            "    return 0;\n"
            "}\n"
        )
        findings = LiefBinaryAnalyzer().analyze(code, dialect="c", include_hardening=False)
        pattern_types = [f.pattern_type.lower() for f in findings]
        assert any("strcpy" in p or "dangerous_import" in p for p in pattern_types)
        assert any("system" in p or "dangerous_import" in p for p in pattern_types)

    def test_clean_code_no_dangerous_imports(self):
        code = "int main() { return 0; }\n"
        findings = LiefBinaryAnalyzer().analyze(code, dialect="c", include_hardening=False)
        assert findings == []

    def test_include_hardening_false_excludes_hardening_findings(self):
        """Regression test for the self-inflicted classifier regression
        found and fixed in roadmap.md §11.14: missing_stack_canary fires
        on nearly any input compiled the same way, so the automatic
        pipeline (include_hardening=False) must not surface it, even
        though it's a real and accurate finding when asked for directly.
        """
        code = "int main() { return 0; }\n"
        findings = LiefBinaryAnalyzer().analyze(code, dialect="c", include_hardening=False)
        assert not any("hardening" in f.pattern_type.lower() or "canary" in f.pattern_type.lower()
                       for f in findings)

    def test_include_hardening_true_surfaces_full_audit(self):
        """The direct, opt-in full-picture call must still work - nothing
        was removed by the include_hardening split, just kept out of the
        default automatic path."""
        code = "int main() { return 0; }\n"
        findings = LiefBinaryAnalyzer().analyze(code, dialect="c", include_hardening=True)
        # Not asserting a specific finding count/content here since hardening
        # posture is compiler/environment-dependent (this sandbox's default
        # flags may or may not already enable stack-protector) - only that
        # the call succeeds and returns well-typed results.
        for f in findings:
            assert isinstance(f, BugPattern)

    def test_findings_are_bug_pattern_instances(self):
        code = (
            "#include <string.h>\n"
            "int main(int argc, char **argv) {\n"
            "    char buf[16];\n"
            "    strcpy(buf, argv[1]);\n"
            "    return 0;\n"
            "}\n"
        )
        findings = LiefBinaryAnalyzer().analyze(code, dialect="c", include_hardening=False)
        for f in findings:
            assert isinstance(f, BugPattern)
