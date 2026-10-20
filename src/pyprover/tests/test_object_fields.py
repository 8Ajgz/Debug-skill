"""self.field reads in methods: fields are fixed symbols for the call.

Writes to fields, calls on self, passing self on, and fields of unknown type are
rejected. Each translated method is also checked against Python on concrete objects.
"""

import ast

import pytest
import z3

from ..equivalence_verifier import (
    _SelfRef,
    _class_fields,
    _find_function,
    _function_to_symbolic,
    _method_owner,
    simplify_function,
    verify_function_equivalence,
)

CLASS = '''class C:
    def __init__(self):
        self.n = 0
        self.flag = True
        self.items: list[int] = []
        self.name: str = "a"
    def f(self, x: int):
        return self.n + x
    def g(self, x: int):
        return x + self.n
    def first(self):
        return self.items[0] if len(self.items) > 0 else -1
    def has_name(self):
        return self.name == "a"
'''


def _py_object(code, attrs):
    ns = {}
    exec(code, ns)
    obj = ns[code.split("class ")[1].split(":")[0].split("(")[0].strip()]()
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


def _z3_value(code, method, attrs, args):
    """Translate the method, fix the fields and arguments, and read the result."""
    node = _find_function(code, method)
    owner = _method_owner(code, method, node.lineno)
    facts, cache = [], {}
    fields = _class_fields(owner)
    env = {node.args.args[0].arg: _SelfRef(fields, cache, facts)}
    for arg in node.args.args[1:]:
        env[arg.arg] = z3.Int(arg.arg)
    expr = _function_to_symbolic(node, env, 64, facts)
    s = z3.Solver()
    for f in facts:
        if not isinstance(f, str):
            s.add(f)
    for attr, value in attrs.items():
        term = cache.get(attr)
        if term is None:
            continue
        if hasattr(term, "length"):
            s.add(term.length == len(value))
            for i, v in enumerate(value):
                s.add(z3.Select(term.items, i) == v)
        else:
            s.add(term == value)
    for arg, value in zip(node.args.args[1:], args):
        s.add(env[arg.arg] == value)
    assert s.check() == z3.sat
    return s.model().eval(expr, model_completion=True)


class TestReads:

    def test_fields_read_in_equivalent_methods(self):
        r = verify_function_equivalence(CLASS, "f", CLASS, "g")
        assert r.equivalent is True, r.summary()

    @pytest.mark.parametrize("n,x", [(0, 3), (5, -2), (-4, 4)])
    def test_translation_matches_python(self, n, x):
        obj = _py_object(CLASS, {"n": n})
        assert _z3_value(CLASS, "f", {"n": n}, [x]).as_long() == obj.f(x)

    @pytest.mark.parametrize("items", [[], [7], [3, 9]])
    def test_list_field_matches_python(self, items):
        obj = _py_object(CLASS, {"items": items})
        assert _z3_value(CLASS, "first", {"items": items}, []).as_long() == obj.first()

    def test_guard_on_list_field_needs_no_domain_note_beyond_lengths(self):
        r = simplify_function(CLASS, "first")
        assert r.status in ("simplified", "already_simplest"), r.summary()

    def test_method_on_different_classes_cannot_be_compared(self):
        other = CLASS.replace("class C:", "class D:")
        combined = CLASS + "\n" + other.split("\n", 0)[0]
        r = verify_function_equivalence(CLASS, "f", other, "f")
        assert r.status == "unsupported"


class TestRejected:

    def test_container_field_write_rejected(self):
        code = CLASS.replace("    def f(self, x: int):\n        return self.n + x\n",
                             "    def f(self, x: int):\n        self.items[0] = 1\n        return 0\n")
        r = simplify_function(code, "f")
        assert r.status == "unsupported", r.summary()

    def test_unannotated_field_written_a_non_literal_is_rejected(self):
        """The type of a field written from a value of unknown type is not known, so the
        model asks for an annotation rather than guessing."""
        code = CLASS.replace("        return self.n + x\n", "        self.n = x\n        return 0\n")
        code = code.replace("def f(self, x: int):", "def f(self, x):")
        r = simplify_function(code, "f")
        assert r.status == "unsupported"
        assert "annotate it" in r.reason

    def test_field_inferred_from_annotated_parameter(self):
        """self.n = x with x: int takes the parameter's type, so no annotation is needed."""
        code = CLASS.replace("        return self.n + x\n", "        self.n = x\n        return 0\n")
        r = simplify_function(code, "f")
        assert r.status in ("simplified", "already_simplest"), r.summary()

    def test_write_of_another_type_rejected(self):
        code = CLASS.replace("        return self.n + x\n", "        self.n = 'a'\n        return 0\n")
        r = simplify_function(code, "f")
        assert r.status == "unsupported"

    def test_method_call_on_self_rejected(self):
        code = CLASS.replace("        return self.n + x\n", "        return self.helper(x)\n")
        assert simplify_function(code, "f").status == "unsupported"

    def test_self_as_value_rejected(self):
        code = CLASS.replace("        return self.n + x\n", "        return self\n")
        r = simplify_function(code, "f")
        assert r.status == "unsupported"
        assert "'self' used as a value" in r.reason

    def test_unknown_field_rejected(self):
        code = CLASS.replace("        return self.n + x\n", "        return self.missing + x\n")
        r = simplify_function(code, "f")
        assert r.status == "unsupported"
        assert "no modelled type" in r.reason

    def test_field_also_a_method_rejected(self):
        code = ("class C:\n    def __init__(self):\n        self.size = 3\n"
                "    def size(self):\n        return 1\n"
                "    def f(self):\n        return self.size\n")
        r = simplify_function(code, "f")
        assert r.status == "unsupported"
        assert "method or property" in r.reason

    def test_conflicting_field_types_rejected(self):
        code = ("class C:\n    def __init__(self):\n        self.v = 1\n"
                "    def set(self):\n        self.v = 'a'\n"
                "    def f(self):\n        return self.v\n")
        r = simplify_function(code, "f")
        assert r.status == "unsupported"

    def test_empty_list_field_needs_annotation(self):
        code = ("class C:\n    def __init__(self):\n        self.items = []\n"
                "    def f(self):\n        return len(self.items)\n")
        r = simplify_function(code, "f")
        assert r.status == "unsupported"
        assert "needs an annotation" in r.reason


def _z3_run(code, method, attrs, args):
    """Run the method symbolically with fixed field values. Returns (return value, final fields)."""
    from ..equivalence_verifier import _final_field
    node = _find_function(code, method)
    owner = _method_owner(code, method, node.lineno)
    facts, cache, exits = [], {}, []
    env = {node.args.args[0].arg: _SelfRef(_class_fields(owner), cache, facts)}
    for arg in node.args.args[1:]:
        env[arg.arg] = z3.Int(arg.arg)
    expr = _function_to_symbolic(node, env, 64, facts, exits)
    s = z3.Solver()
    for f in facts:
        if not isinstance(f, str):
            s.add(f)
    for attr, value in attrs.items():
        if attr in cache:
            s.add(cache[attr] == value)
    for arg, value in zip(node.args.args[1:], args):
        s.add(env[arg.arg] == value)
    assert s.check() == z3.sat
    m = s.model()
    final = {k: m.eval(_final_field(exits, k, cache[k]), model_completion=True) for k in cache
             if isinstance(cache[k], z3.ExprRef)}
    return m.eval(expr, model_completion=True), {k: v for k, v in final.items()}


WRITES = """class W:
    def __init__(self):
        self.n: int = 0
        self.flag: bool = True
    def set_n(self, x: int):
        self.n = x
        return 0
    def bump(self, x: int):
        self.n += x
        return self.n
    def branch(self, x: int):
        if x > 0:
            self.n = 1
        return self.n
    def pair(self, x: int):
        self.n, self.flag = x, False
        return self.n
"""


PAIR = WRITES.rstrip() + """
    def set_a(self, x: int):
        self.n = x
        return 0
    def set_b(self, x: int):
        self.n = x + 0
        return 0
    def set_none(self, x: int):
        return 0
"""


class TestWrites:

    def test_write_then_return_is_supported(self):
        r = simplify_function(WRITES, "set_n")
        assert r.status in ("simplified", "already_simplest"), r.summary()

    def test_equal_final_state_is_proven(self):
        r = verify_function_equivalence(PAIR, "set_a", PAIR, "set_b")
        assert r.equivalent is True, r.summary()

    def test_different_final_state_is_not_equivalent(self):
        """Both return 0, but only one writes the field, so the objects end in different states."""
        r = verify_function_equivalence(PAIR, "set_a", PAIR, "set_none")
        assert r.equivalent is False, r.summary()

    @pytest.mark.parametrize("n,x", [(0, 3), (5, -2), (-4, 4)])
    def test_augmented_write_matches_python(self, n, x):
        obj = _py_object(WRITES, {"n": n})
        value, final = _z3_run(WRITES, "bump", {"n": n}, [x])
        expected = obj.bump(x)
        assert value.as_long() == expected
        assert final["n"].as_long() == obj.n

    @pytest.mark.parametrize("x", [-1, 0, 4])
    def test_write_in_branch_matches_python(self, x):
        obj = _py_object(WRITES, {"n": 9})
        value, final = _z3_run(WRITES, "branch", {"n": 9}, [x])
        assert value.as_long() == obj.branch(x)
        assert final["n"].as_long() == obj.n

    @pytest.mark.parametrize("x", [2, -3])
    def test_tuple_write_matches_python(self, x):
        obj = _py_object(WRITES, {"n": 0, "flag": True})
        value, final = _z3_run(WRITES, "pair", {"n": 0, "flag": True}, [x])
        assert value.as_long() == obj.pair(x)
        assert final["n"].as_long() == obj.n
        assert z3.is_false(final["flag"])


class TestOptionalField:

    CODE = ("class C:\n    def __init__(self):\n        self.v: Optional[int] = None\n"
            "    def f(self):\n        return 0 if self.v is None else self.v + 1\n")

    def test_none_guard_on_field(self):
        r = simplify_function(self.CODE, "f")
        assert r.status in ("simplified", "already_simplest"), r.summary()

    def test_unguarded_optional_field_rejected(self):
        code = self.CODE.replace("0 if self.v is None else self.v + 1", "self.v + 1")
        assert simplify_function(code, "f").status == "unsupported"
