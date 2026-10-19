"""Property testing for JavaScript (node) and Rust (rustc) contracts.

Each case is also run through the Python tester where the same logic applies, so the
three languages must agree on the verdict.
"""
import shutil

import pytest

from ..property_tester import property_test
from ..property_tester_lang import property_test_js, property_test_rust

pytestmark = pytest.mark.verification
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
needs_rustc = pytest.mark.skipif(shutil.which("rustc") is None, reason="rustc not installed")

JS_BUGGY = "// Pre: x > 0\n// Post: result > 0\nfunction f(x) {\n  return x - 1;\n}\n"
JS_FIXED = "// Pre: x > 0\n// Post: result > 0\nfunction f(x) {\n  return x;\n}\n"
RS_BUGGY = "// Pre: x > 0\n// Post: result > 0\nfn f(x: i64) -> i64 {\n    x - 1\n}\n"
RS_FIXED = "// Pre: x > 0\n// Post: result > 0\nfn f(x: i64) -> i64 {\n    x\n}\n"


@needs_node
class TestJavaScript:
    def test_bug_found_with_counterexample(self):
        outcome = property_test_js(JS_BUGGY)
        assert outcome["status"] == "failed"
        assert outcome["counterexample"] == {"x": 1}

    def test_fix_passes(self):
        outcome = property_test_js(JS_FIXED)
        assert outcome["status"] == "passed"
        assert outcome["examples"] > 0

    def test_exception_is_a_failure(self):
        code = "// Pre: x > 0\n// Post: result >= 0\nfunction g(x) {\n  if (x === 1) throw new Error('boom');\n  return x;\n}\n"
        outcome = property_test_js(code)
        assert outcome["status"] == "failed"
        assert "raised" in outcome["reason"]
        assert outcome["counterexample"] == {"x": 1}

    def test_floor_division_and_modulo_follow_python(self):
        code = "// Post: x // 2 * 2 + x % 2 == x\nfunction h(x) {\n  return x;\n}\n"
        assert property_test_js(code)["status"] == "passed"

    def test_conditional_postcondition(self):
        code = "// Pre: x > 0\n// Post: if x > 5: result > 0\nfunction k(x) {\n  return x;\n}\n"
        assert property_test_js(code)["status"] == "passed"

    def test_agrees_with_python_tester(self):
        python = "# Pre: x > 0\n# Post: result > 0\ndef f(x):\n    return x - 1\n"
        assert property_test(python)["status"] == property_test_js(JS_BUGGY)["status"] == "failed"

    def test_unsupported_clause_is_skipped(self):
        code = "// Post: x ** 2 >= 0\nfunction s(x) {\n  return x;\n}\n"
        assert property_test_js(code)["status"] == "skipped"

    def test_no_function_is_skipped(self):
        assert property_test_js("// Post: x > 0\nconst y = 1;\n")["status"] == "skipped"


@needs_rustc
class TestRust:
    def test_bug_found_with_counterexample(self):
        outcome = property_test_rust(RS_BUGGY)
        assert outcome["status"] == "failed"
        assert outcome["counterexample"] == {"x": 1}

    def test_fix_passes(self):
        outcome = property_test_rust(RS_FIXED)
        assert outcome["status"] == "passed"
        assert outcome["examples"] > 0

    def test_panic_is_a_failure(self):
        code = ("// Pre: x > 0\n// Post: result >= 0\nfn p(x: i64) -> i64 {\n"
                "    if x == 1 { panic!(\"boom\"); }\n    x\n}\n")
        outcome = property_test_rust(code)
        assert outcome["status"] == "failed"
        assert outcome["reason"] == "panicked"
        assert outcome["counterexample"] == {"x": 1}

    def test_f64_parameter_uses_real_division(self):
        code = "// Pre: x > 0.5\n// Post: result >= 0\nfn g(x: f64) -> f64 {\n    x / 2.0\n}\n"
        assert property_test_rust(code)["status"] == "passed"

    def test_floor_division_follows_python(self):
        code = "// Post: x // 2 * 2 + x % 2 == x\nfn h(x: i64) -> i64 {\n    x\n}\n"
        assert property_test_rust(code)["status"] == "passed"

    def test_agrees_with_javascript(self):
        assert property_test_rust(RS_BUGGY)["status"] == property_test_js(JS_BUGGY)["status"] == "failed"

    def test_unsupported_parameter_type_is_skipped(self):
        code = "// Post: result >= 0\nfn b(flag: bool) -> i64 {\n    1\n}\n"
        assert property_test_rust(code)["status"] == "skipped"

    def test_result_without_return_type_is_skipped(self):
        code = "// Post: result >= 0\nfn u(x: i64) {\n    let _ = x;\n}\n"
        assert property_test_rust(code)["status"] == "skipped"

    def test_compile_error_is_skipped_not_passed(self):
        code = "// Post: result >= 0\nfn broken(x: i64) -> i64 {\n    x +\n}\n"
        outcome = property_test_rust(code)
        assert outcome["status"] == "skipped"
        assert "could not build" in outcome["reason"]
