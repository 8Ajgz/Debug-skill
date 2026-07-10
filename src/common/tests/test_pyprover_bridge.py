"""
Regression tests for common/pyprover_bridge.py.

Covers the v2.5.2-sibling-branch reconciliation fix: `_map_language_type`
must accept a `LanguageType` enum directly (returning it unchanged), not
just a lowercase language string. Before the fix, any caller that already
had a `LanguageType` (rather than a raw PyProver language string) would
fail `.lower()` with an AttributeError, since `LanguageType` members are
not strings.
"""

import pytest
from common.pyprover_bridge import PyProverBridge
from common.interop import LanguageType


@pytest.fixture
def bridge():
    return PyProverBridge()


class TestMapLanguageType:

    def test_accepts_string(self, bridge):
        assert bridge._map_language_type("python") == LanguageType.PYTHON
        assert bridge._map_language_type("csharp") == LanguageType.CSHARP
        assert bridge._map_language_type("c#") == LanguageType.CSHARP

    def test_accepts_string_case_insensitive(self, bridge):
        assert bridge._map_language_type("PYTHON") == LanguageType.PYTHON

    def test_accepts_language_type_directly(self, bridge):
        """Regression: passing a LanguageType enum member must return it
        unchanged, not raise AttributeError from calling .lower() on it."""
        assert bridge._map_language_type(LanguageType.RUST) == LanguageType.RUST
        assert bridge._map_language_type(LanguageType.CPP) == LanguageType.CPP

    def test_unknown_string_returns_none(self, bridge):
        assert bridge._map_language_type("cobol") is None


class TestVerifyEquivalenceBridge:

    def test_equivalent_functions_via_bridge(self, bridge):
        verbose = (
            "def f(x):\n"
            "    if x > 0:\n"
            "        if x > 100:\n"
            "            return 1\n"
            "        else:\n"
            "            return 1\n"
            "    else:\n"
            "        return 0\n"
        )
        simple = "def g(x):\n    if x > 0:\n        return 1\n    else:\n        return 0\n"
        result = bridge.verify_equivalence(verbose, "f", simple, "g")
        assert result is not None
        assert result["status"] == "decided"
        assert result["equivalent"] is True

    def test_non_equivalent_functions_via_bridge(self, bridge):
        a = "def f(x):\n    if x > 0:\n        return 1\n    else:\n        return -1\n"
        b = "def g(x):\n    return 1\n"
        result = bridge.verify_equivalence(a, "f", b, "g")
        assert result is not None
        assert result["status"] == "decided"
        assert result["equivalent"] is False
        assert result["counterexample"] is not None

    def test_unsupported_construct_via_bridge_not_none(self, bridge):
        """An out-of-scope construct must surface as
        status='unsupported', not a bare None - None is reserved for
        'pyprover itself is unavailable', a different failure mode callers
        need to distinguish."""
        code = "def f(x):\n    return x.some_attr\n"
        result = bridge.verify_equivalence(code, "f", code, "f")
        assert result is not None
        assert result["status"] == "unsupported"


class TestSimplifyFunctionCodeBridge:

    def test_redundant_branches_simplified_via_bridge(self, bridge):
        code = (
            "def f(x):\n"
            "    if x > 0:\n"
            "        if x > 100:\n"
            "            return 1\n"
            "        else:\n"
            "            return 1\n"
            "    else:\n"
            "        return 0\n"
        )
        result = bridge.simplify_function_code(code, "f")
        assert result is not None
        assert result["status"] == "simplified"
        assert result["simplified_expr"] is not None
        assert result["simplified_expr"] != result["original_expr"]
