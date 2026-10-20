"""Class and call models: objects, enums, inlined calls, properties, and cross-file scopes.

Each result that renders as Python is checked by running the original function and the
rendered expression on the same inputs. Objects are plain namespaces with the fields the
class declares, and enum values are the real members of the enum the code defines.
"""

import itertools
import types

from src.pyprover.equivalence_verifier import (
    simplify_function,
    verify_function_equivalence,
)
from src.pyprover.project_index import ProjectScope

COUNTER = '''
class Counter:
    count: int
    step: int
'''

ENUM = '''
from enum import Enum

class Color(Enum):
    RED = 1
    GREEN = 2
    BLUE = 3
'''


def _run(code, func_name, args):
    ns = {}
    exec(code, ns)
    return ns[func_name](*args)


def _check_rendered(code, func_name, cases, scope=None):
    """Assert the simplifier's Python rendering agrees with the original on every case."""
    r = simplify_function(code, func_name, scope=scope)
    assert r.status in ("simplified", "already_simplest"), r.reason
    if r.simplified_python is None:
        return r  # no Python form is claimed, so there is nothing to run
    ns = {}
    exec(code, ns)
    func = ns[func_name]
    params = [a for a in func.__code__.co_varnames[:func.__code__.co_argcount]]
    for args in cases:
        expected = func(*args)
        got = eval(r.simplified_python, {}, dict(zip(params, args)))
        assert got == expected, f"{r.simplified_python} gave {got}, original gave {expected} on {args}"
    return r


# --- calls to functions -------------------------------------------------------

def test_call_to_module_function_is_inlined():
    code = '''
def double(x):
    return x * 2

def f(x):
    return double(x) + 0
'''
    r = simplify_function(code, "f")
    assert r.status == "simplified", r.reason
    _check_rendered(code, "f", [(i,) for i in range(-3, 4)])


def test_call_result_is_proven_equal_to_inline_expression():
    code = '''
def double(x):
    return x * 2

def f(x):
    return double(x)
'''
    other = '''
def g(x):
    return x + x
'''
    assert verify_function_equivalence(code, "f", other, "g").equivalent is True


def test_call_to_function_with_free_global_is_rejected():
    code = '''
K = 3

def helper(x):
    return x + K

def f(x):
    return helper(x)
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "neither a parameter nor a local" in r.reason


def test_recursive_call_is_rejected():
    code = '''
def fact(n):
    if n <= 0:
        return 1
    return n * fact(n - 1)
'''
    r = simplify_function(code, "fact")
    assert r.status == "unsupported"
    assert "recursive" in r.reason


def test_call_with_missing_argument_is_rejected():
    code = '''
def add(a, b):
    return a + b

def f(x):
    return add(x)
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "does not pass 'b'" in r.reason


def test_call_with_default_uses_the_literal_default():
    code = '''
def scale(x, k=3):
    return x * k

def f(x):
    return scale(x) + 0
'''
    _check_rendered(code, "f", [(i,) for i in range(-3, 4)])


def test_decorated_function_is_not_inlined():
    # A decorator may replace the body, so the body is not necessarily what a call runs.
    code = '''
def wrap(fn):
    return lambda x: 0

@wrap
def scale(x):
    return x * 2

def f(x):
    return scale(x) + 0
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "decorated" in r.reason


def test_keyword_argument_is_rejected():
    code = '''
def scale(x, k):
    return x * k

def f(x):
    return scale(x, k=2)
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "keyword" in r.reason


# --- objects ------------------------------------------------------------------

def test_object_field_read_renders_as_attribute():
    code = COUNTER + '''
def f(c: Counter):
    return c.count * 1 + c.step * 0
'''
    r = simplify_function(code, "f")
    assert r.status == "simplified", r.reason
    assert r.simplified_python == "c.count"
    _check_rendered(code, "f", [(types.SimpleNamespace(count=n, step=s),) for n in range(-2, 3) for s in range(-2, 3)])


def test_object_argument_passed_to_function_reads_the_same_fields():
    code = COUNTER + '''
def total(c: Counter):
    return c.count + c.step

def f(c: Counter):
    return total(c) + 0
'''
    cases = [(types.SimpleNamespace(count=a, step=b),) for a in range(-2, 3) for b in range(-2, 3)]
    _check_rendered(code, "f", cases)


def test_object_argument_of_the_wrong_class_is_rejected():
    code = COUNTER + '''
class Other:
    count: int

def total(c: Counter):
    return c.count

def f(o: Other):
    return total(o)
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "same class" in r.reason


def test_writing_a_parameter_field_is_rejected():
    code = COUNTER + '''
def f(c: Counter):
    c.count = 5
    return c.count
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "object fields" in r.reason


def test_object_used_as_a_value_is_rejected():
    code = COUNTER + '''
def g(c: Counter):
    return c.count

def f(c: Counter):
    return c
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "used as a value" in r.reason


def test_object_field_of_unmodelled_type_is_rejected_on_read():
    code = '''
class Holder:
    items: list

def f(h: Holder):
    return h.items
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"


# --- methods of self, and properties ------------------------------------------

def test_self_method_call_is_inlined_and_sees_fields():
    code = '''
class Box:
    n: int

    def scale(self, k):
        return self.n * k

    def f(self, k):
        return self.scale(k) + 0
'''
    r = simplify_function(code, "f")
    assert r.status == "simplified", r.reason
    ns = {}
    exec(code, ns)
    box = ns["Box"]
    for n in range(-2, 3):
        for k in range(-2, 3):
            obj = box()
            obj.n = n
            got = eval(r.simplified_python, {}, {"self": obj, "k": k})
            assert got == box.f(obj, k)


def test_self_method_sees_a_field_written_before_the_call():
    code = '''
class Box:
    n: int

    def get(self):
        return self.n

    def f(self, k):
        self.n = k
        return self.get()
'''
    r = simplify_function(code, "f")
    assert r.original_expr == "k"


def test_method_that_writes_fields_is_not_inlined():
    code = '''
class Box:
    n: int

    def bump(self):
        self.n = self.n + 1
        return self.n

    def f(self):
        return self.bump() + 0
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "writes a field" in r.reason


def test_property_read_is_inlined():
    code = '''
class Pair:
    a: int
    b: int

    @property
    def total(self):
        return self.a + self.b

    def f(self):
        return self.total + 0
'''
    r = simplify_function(code, "f")
    assert r.status == "simplified", r.reason
    assert "self.a" in r.simplified_python and "self.b" in r.simplified_python


def test_method_overridden_by_a_subclass_is_not_inlined():
    code = '''
class Base:
    n: int

    def value(self):
        return self.n

class Sub(Base):
    def value(self):
        return self.n + 100

def f(b: Base):
    return b.value()
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "overridden by a subclass" in r.reason


def test_field_redefined_by_a_subclass_property_is_not_read():
    code = '''
class Base:
    n: int

class Sub(Base):
    @property
    def n(self):
        return 0

def f(b: Base):
    return b.n + 0
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "overridden by a subclass" in r.reason


# --- enums --------------------------------------------------------------------

def test_enum_comparison_is_identity_on_members():
    # Both functions are in one code string, so their Color is one class definition.
    code = ENUM + '''
def is_red(c: Color):
    return c == Color.RED

def is_red_by_identity(c: Color):
    return c is Color.RED
'''
    assert verify_function_equivalence(code, "is_red", code, "is_red_by_identity").equivalent is True


def test_enum_domain_is_only_its_members():
    # Color has three members. On each of them, "not GREEN" is "RED or BLUE", but
    # "always true" differs at GREEN, so the proof depends on the member domain.
    code = ENUM + '''
def not_green(c: Color):
    return c != Color.GREEN

def red_or_blue(c: Color):
    return c == Color.RED or c == Color.BLUE

def always(c: Color):
    return True
'''
    assert verify_function_equivalence(code, "not_green", code, "red_or_blue").equivalent is True
    assert verify_function_equivalence(code, "not_green", code, "always").equivalent is False


def test_enum_member_used_as_a_value_is_rejected():
    code = ENUM + '''
def f(c: Color):
    return Color.RED
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"
    assert "only modelled in a comparison" in r.reason


def test_enum_value_returned_is_rejected():
    code = ENUM + '''
def f(c: Color):
    return c
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"


def test_enum_with_duplicate_values_is_not_modelled_as_an_enum():
    code = '''
from enum import Enum

class Alias(Enum):
    A = 1
    B = 1

def f(c: Alias):
    return c == Alias.A
'''
    r = simplify_function(code, "f")
    assert r.status == "unsupported"


def test_enum_rendering_is_checked_against_real_members():
    code = ENUM + '''
def pick(c: Color, x: int):
    return (x + 1 + 0) if c == Color.RED else (x + 2)
'''
    ns = {}
    exec(code, ns)
    members = {1: ns["Color"].RED, 2: ns["Color"].GREEN, 3: ns["Color"].BLUE}
    r = simplify_function(code, "pick")
    assert r.status in ("simplified", "already_simplest"), r.reason
    if r.simplified_python is not None:
        for index, x in itertools.product((1, 2, 3), range(-2, 3)):
            got = eval(r.simplified_python, {}, {"c": members[index], "x": x})
            assert got == ns["pick"](members[index], x)


# --- project scope -------------------------------------------------------------

def test_class_imported_from_another_file_is_modelled(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from .types import Counter\n")
    (pkg / "types.py").write_text("class Counter:\n    count: int\n    step: int\n")
    (pkg / "user.py").write_text(
        "from .types import Counter\n\n"
        "def f(c: Counter):\n"
        "    return c.count * 1\n"
    )
    scope = ProjectScope(str(tmp_path), "pkg/user.py")
    code = (pkg / "user.py").read_text()
    r = simplify_function(code, "f", scope=scope)
    assert r.status == "simplified", r.reason
    assert r.simplified_python == "c.count"


def test_class_reached_through_package_reexport(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from .types import Counter\n")
    (pkg / "types.py").write_text("class Counter:\n    count: int\n")
    (pkg / "user.py").write_text("from pkg import Counter\n\ndef f(c: Counter):\n    return c.count + 0\n")
    scope = ProjectScope(str(tmp_path), "pkg/user.py")
    assert scope.class_def("Counter") is not None


def test_name_not_in_repository_is_not_resolved(tmp_path):
    (tmp_path / "user.py").write_text(
        "from somewhere_else import Thing\n\ndef f(t: Thing):\n    return t.x\n")
    scope = ProjectScope(str(tmp_path), "user.py")
    assert scope.class_def("Thing") is None
    r = simplify_function((tmp_path / "user.py").read_text(), "f", scope=scope)
    assert r.status == "unsupported"


def test_subclass_in_another_file_blocks_inlining(tmp_path):
    (tmp_path / "base.py").write_text(
        "class Base:\n    n: int\n\n    def value(self):\n        return self.n\n")
    (tmp_path / "sub.py").write_text(
        "from base import Base\n\nclass Sub(Base):\n    def value(self):\n        return 0\n")
    (tmp_path / "user.py").write_text(
        "from base import Base\n\ndef f(b: Base):\n    return b.value()\n")
    scope = ProjectScope(str(tmp_path), "user.py")
    r = simplify_function((tmp_path / "user.py").read_text(), "f", scope=scope)
    assert r.status == "unsupported"
    assert "overridden by a subclass" in r.reason


def test_scope_records_that_a_local_class_is_taken_as_closed():
    code = COUNTER + '''
def value(c: Counter):
    return c.count + 0
'''
    r = simplify_function(code, "value")
    assert r.status == "simplified"
    assert r.domain is not None and "no subclass is in the analysed code" in r.domain
