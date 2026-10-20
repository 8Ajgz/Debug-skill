"""Records: a dataclass built by a constructor call is compared field by field.

Each equivalence this model claims is checked against Python's own `==` on the same
inputs, since a dataclass compares by its fields.
"""

from src.pyprover.equivalence_verifier import simplify_function, verify_function_equivalence
from src.pyprover.project_index import ProjectScope

PAIR = '''
from dataclasses import dataclass

@dataclass
class Pair:
    a: int
    b: int
'''


def _ns(code):
    ns = {}
    exec(code, ns)
    return ns


def _assert_python_agrees(code, f, g, xs):
    """Where the model says two functions return equal records, Python's == agrees."""
    ns = _ns(code)
    for x in xs:
        assert ns[f](x) == ns[g](x), f"{f}({x}) and {g}({x}) differ in Python"


def test_equal_records_by_positional_and_keyword_arguments():
    code = PAIR + '''
def mk(x):
    return Pair(a=x, b=x + 1)

def mk2(x):
    return Pair(x, x + 1)
'''
    r = verify_function_equivalence(code, "mk", code, "mk2")
    assert r.equivalent is True, r.summary()
    _assert_python_agrees(code, "mk", "mk2", range(-3, 4))


def test_records_differing_in_one_field_are_not_equal():
    code = PAIR + '''
def mk(x):
    return Pair(a=x, b=x + 1)

def mk2(x):
    return Pair(a=x, b=x + 2)
'''
    r = verify_function_equivalence(code, "mk", code, "mk2")
    assert r.equivalent is False
    assert r.counterexample is not None


def test_branches_returning_records_join_field_by_field():
    code = PAIR + '''
def pick(x):
    if x > 0:
        return Pair(a=1, b=x)
    return Pair(a=2, b=x)

def pick2(x):
    return Pair(a=1 if x > 0 else 2, b=x)
'''
    r = verify_function_equivalence(code, "pick", code, "pick2")
    assert r.equivalent is True, r.summary()
    _assert_python_agrees(code, "pick", "pick2", range(-3, 4))


def test_record_bound_to_a_name_and_read_field_by_field():
    code = PAIR + '''
def f(x):
    p = Pair(a=x, b=2)
    return p.a + p.b

def g(x):
    return x + 2
'''
    r = verify_function_equivalence(code, "f", code, "g")
    assert r.equivalent is True, r.summary()
    _assert_python_agrees(code, "f", "g", range(-3, 4))


def test_record_branches_merged_when_bound_in_both():
    code = PAIR + '''
def f(x):
    if x > 0:
        p = Pair(a=1, b=x)
    else:
        p = Pair(a=2, b=x)
    return p

def g(x):
    return Pair(a=1 if x > 0 else 2, b=x)
'''
    r = verify_function_equivalence(code, "f", code, "g")
    assert r.equivalent is True, r.summary()


def test_dataclass_with_its_own_init_sets_fields():
    code = '''
from dataclasses import dataclass

@dataclass
class Span:
    lo: int
    hi: int

    def __init__(self, x):
        self.lo = x
        if x > 0:
            self.hi = x * 2
        else:
            self.hi = 0

def f(x):
    return Span(x)

def g(x):
    return Span(x=x)

def h(x):
    return Span(x + 0)

def other(x):
    return Span(x + 1)
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    assert verify_function_equivalence(code, "f", code, "h").equivalent is True
    assert verify_function_equivalence(code, "f", code, "other").equivalent is False
    _assert_python_agrees(code, "f", "h", range(-3, 4))


def test_field_default_is_used_when_not_passed():
    code = '''
from dataclasses import dataclass

@dataclass
class Opts:
    level: int = 3
    flag: bool = False

def f(x):
    return Opts(x)

def g(x):
    return Opts(x, False)

def h(x):
    return Opts(level=x, flag=False)

def k(x):
    return Opts(x, True)
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    assert verify_function_equivalence(code, "f", code, "h").equivalent is True
    assert verify_function_equivalence(code, "f", code, "k").equivalent is False
    _assert_python_agrees(code, "f", "g", range(-3, 4))


def test_record_is_only_compared_not_simplified():
    code = PAIR + '''
def f(x):
    return Pair(a=x, b=0)
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "compared field by field" in r.reason


def test_constructor_inside_an_expression_is_rejected():
    code = PAIR + '''
def f(x):
    return Pair(x, 1).a
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "whole return" in r.reason


def test_plain_class_is_not_compared_by_fields():
    code = '''
class Plain:
    def __init__(self, a):
        self.a = a

def f(x):
    return Plain(x)

def g(x):
    return Plain(x)
'''
    r = verify_function_equivalence(code, "f", code, "g")
    assert r.equivalent is None
    assert "not a dataclass" in r.reason


def test_dataclass_with_eq_false_is_not_compared_by_fields():
    code = '''
from dataclasses import dataclass

@dataclass(eq=False)
class Pair:
    a: int

def f(x):
    return Pair(x)

def g(x):
    return Pair(x)
'''
    r = verify_function_equivalence(code, "f", code, "g")
    assert "eq=False" in r.reason


def test_missing_argument_without_default_is_rejected():
    code = PAIR + '''
def f(x):
    return Pair(a=x)
'''
    r = verify_function_equivalence(code, "f", code, "f")
    assert r.status == "unsupported"
    assert "does not pass 'b'" in r.reason


def test_unknown_keyword_is_rejected():
    code = PAIR + '''
def f(x):
    return Pair(a=x, c=1)

def g(x):
    return Pair(a=x, b=1)
'''
    r = verify_function_equivalence(code, "f", code, "g")
    assert r.status == "unsupported"
    assert "names no parameter" in r.reason


def test_init_that_reads_a_field_before_setting_it_is_rejected():
    code = '''
from dataclasses import dataclass

@dataclass
class Box:
    n: int

    def __init__(self, x):
        self.n = self.n + x

def f(x):
    return Box(x)
'''
    r = verify_function_equivalence(code, "f", code, "f")
    assert r.status == "unsupported"
    assert "reads a field" in r.reason


def test_non_scalar_field_is_rejected():
    code = '''
from dataclasses import dataclass

@dataclass
class Bag:
    items: list

def f(x):
    return Bag(x)
'''
    r = verify_function_equivalence(code, "f", code, "f")
    assert r.status == "unsupported"
    assert "not a scalar" in r.reason


def test_records_of_different_classes_are_not_compared():
    code = PAIR + '''
@dataclass
class Other:
    a: int
    b: int

def f(x):
    return Pair(x, x)

def g(x):
    return Other(x, x)
'''
    r = verify_function_equivalence(code, "f", code, "g")
    assert r.status == "unsupported"
    assert "different classes" in r.reason


def test_record_across_files_resolves_through_project_scope(tmp_path):
    (tmp_path / "shapes.py").write_text(
        "from dataclasses import dataclass\n\n@dataclass\nclass Pair:\n    a: int\n    b: int\n")
    (tmp_path / "user.py").write_text(
        "from shapes import Pair\n\n"
        "def f(x):\n    return Pair(a=x, b=x + 1)\n\n"
        "def g(x):\n    return Pair(x, x + 1)\n")
    scope = ProjectScope(str(tmp_path), "user.py")
    code = (tmp_path / "user.py").read_text()
    r = verify_function_equivalence(code, "f", code, "g", scope=scope)
    assert r.equivalent is True, r.summary()


LEVEL = '''
from dataclasses import dataclass
from enum import Enum

class Level(Enum):
    LOW = 1
    HIGH = 2

@dataclass
class Item:
    level: Level
    n: int
'''


def test_enum_field_compared_by_member():
    code = LEVEL + '''
def f(x):
    return Item(Level.HIGH if x > 0 else Level.LOW, x)

def g(x):
    return Item(level=Level.HIGH if x > 0 else Level.LOW, n=x)

def h(x):
    return Item(Level.LOW, x)
'''
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    assert verify_function_equivalence(code, "f", code, "h").equivalent is False
    _assert_python_agrees(code, "f", "g", range(-3, 4))


def test_enum_field_default_and_init_branch():
    code = LEVEL + '''
@dataclass
class Tagged:
    level: Level = Level.LOW
    n: int = 0

    def __init__(self, x):
        if x > 0:
            self.level = Level.HIGH
        else:
            self.level = Level.LOW
        self.n = x

def f(x):
    return Tagged(x)

def g(x):
    return Tagged(x=x)

'''
    # Tagged's __init__ sets the level from x, so a keyword call is the same record.
    assert verify_function_equivalence(code, "f", code, "g").equivalent is True
    _assert_python_agrees(code, "f", "g", range(-3, 4))
    ns = _ns(code)
    assert ns["Tagged"](1).level is ns["Level"].HIGH and ns["Tagged"](0).level is ns["Level"].LOW

    # A dataclass without __init__ takes a field's default when the call leaves it out.
    defaulted = LEVEL + '''
@dataclass
class Defaulted:
    level: Level = Level.LOW
    n: int = 0

def d(x):
    return Defaulted(n=x)

def e(x):
    return Defaulted(Level.LOW, x)
'''
    assert verify_function_equivalence(defaulted, "d", defaulted, "e").equivalent is True
    _assert_python_agrees(defaulted, "d", "e", range(-3, 4))
    ns = _ns(defaulted)
    assert ns["Defaulted"](n=1).level is ns["Level"].LOW


def test_dataclass_with_its_own_eq_is_not_compared_by_fields():
    code = '''
from dataclasses import dataclass

@dataclass
class Pair:
    a: int

    def __eq__(self, other):
        return True

def f(x):
    return Pair(x)

def g(x):
    return Pair(x)
'''
    r = verify_function_equivalence(code, "f", code, "g")
    assert r.status == "unsupported"
    assert "defines __eq__" in r.reason
