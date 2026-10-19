"""verify_fix: a fix is accepted only if the original fails its contract and the fix passes it."""
import pytest

from ...pyprover.property_tester import HYPOTHESIS_AVAILABLE
from .. import verify_fix

pytestmark = [pytest.mark.verification,
              pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")]

BUGGY = '@requires("x > 0")\n@ensures("result > 0")\ndef f(x):\n    return x - 1\n'
FIXED = '@requires("x > 0")\n@ensures("result > 0")\ndef f(x):\n    return x\n'
STILL_WRONG = '@requires("x > 0")\n@ensures("result > 0")\ndef f(x):\n    return x - 2\n'
NO_BUG = '@requires("x > 0")\n@ensures("result > 0")\ndef f(x):\n    return x * 2\n'


def test_fix_verified_when_bug_reproduced_and_fixed():
    result = verify_fix(BUGGY, FIXED)
    assert result.bug_reproduced is True
    assert result.counterexample is not None
    assert result.fixed_status == "passed"
    assert result.fix_verified is True


def test_fix_rejected_when_still_violating_contract():
    result = verify_fix(BUGGY, STILL_WRONG)
    assert result.fix_verified is False
    assert "still violates" in result.reason


def test_nothing_to_fix_when_original_passes():
    result = verify_fix(NO_BUG, FIXED)
    assert result.bug_reproduced is False
    assert result.fix_verified is False


def test_untestable_original_is_not_verified():
    result = verify_fix("def f(x):\n    return x\n", FIXED)
    assert result.fix_verified is False
    assert "cannot test" in result.reason


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node not installed")
def test_javascript_fix_verified():
    buggy = "// Pre: x > 0\n// Post: result > 0\nfunction f(x) {\n  return x - 1;\n}\n"
    fixed = "// Pre: x > 0\n// Post: result > 0\nfunction f(x) {\n  return x;\n}\n"
    result = verify_fix(buggy, fixed, language="javascript")
    assert result.fix_verified is True
    assert result.counterexample == {"x": 1}


def test_unknown_language_is_rejected():
    with pytest.raises(ValueError):
        verify_fix(BUGGY, FIXED, language="cobol")
