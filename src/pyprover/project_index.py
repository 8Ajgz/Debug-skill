"""Class and function definitions visible from one source file of a project.

The simplifier models a call or a class by reading its definition. A file usually
gets its classes from other files, through `from .types import VerificationState`
or `from pkg.module import Name`. This module follows those imports inside one
repository and returns the defining AST node. It reads source text only: nothing
is imported or executed.

A name is resolved only when the import can be followed to a file that exists in
the repository. A name imported from outside the repository, a dynamic import,
or a star import is not resolved, so anything that depends on it is not modelled.

The scope also answers which names a subclass in the repository defines. A
subclass can override a method or a property of the class it extends, so the
simplifier must not read one of those names on an object of the base class. The
repository is scanned once for classes that derive from a given name.
"""

import ast
import os
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

_MAX_HOPS = 6  # re-export chains longer than this are not followed

Definition = Union[ast.ClassDef, ast.FunctionDef]


def base_name(node: ast.expr) -> Optional[str]:
    """The name a base-class expression ends in: `Base`, `module.Base` or `Base[T]`."""
    if isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def subclass_members(classes: Iterable[ast.ClassDef], name: str) -> Set[str]:
    """The names that classes deriving from `name` define in their bodies: methods,
    properties and class attributes, for direct and indirect subclasses alike.

    A subclass can override any of these, so a call or a read of one on an object
    whose class is `name` may run the subclass's code instead. Matching is by name,
    so a class of another module with the same name is included too. That widens the
    set, and only ever makes the check reject more.
    """
    classes = list(classes)
    derived = {name}
    grew = True
    while grew:
        grew = False
        for c in classes:
            if c.name not in derived and any(base_name(b) in derived for b in c.bases):
                derived.add(c.name)
                grew = True
    members: Set[str] = set()
    for c in classes:
        if c.name in derived and c.name != name:
            for stmt in c.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.add(stmt.name)
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    members.add(stmt.target.id)
                elif isinstance(stmt, ast.Assign):
                    members.update(t.id for t in stmt.targets if isinstance(t, ast.Name))
    return members


def module_bool_flags(tree: ast.Module) -> Set[str]:
    """Names that a module binds to True or False, and to nothing else.

    A flag is typically set in a try block (`_OK = True` / `except ImportError: _OK = False`).
    A name is excluded if the module also binds it otherwise: by a def, class, import, loop
    or with target, a tuple target, an augmented assignment, or a `global` declaration in any
    function, which could change it at run time.
    """
    flags: Set[str] = set()
    other: Set[str] = set()

    def bind_target(target: ast.expr) -> None:
        for n in ast.walk(target):
            if isinstance(n, ast.Name):
                other.add(n.id)

    def visit(stmts: List[ast.stmt]) -> None:
        for st in stmts:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                other.add(st.name)
            elif isinstance(st, (ast.Import, ast.ImportFrom)):
                other.update((a.asname or a.name).split(".")[0] for a in st.names)
            elif isinstance(st, ast.Assign):
                for t in st.targets:
                    if isinstance(t, ast.Name) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, bool):
                        flags.add(t.id)
                    else:
                        bind_target(t)
            elif isinstance(st, (ast.AnnAssign, ast.AugAssign)):
                bind_target(st.target)
            elif isinstance(st, (ast.For, ast.AsyncFor)):
                bind_target(st.target)
                visit(st.body)
                visit(st.orelse)
            elif isinstance(st, (ast.With, ast.AsyncWith)):
                for item in st.items:
                    if item.optional_vars is not None:
                        bind_target(item.optional_vars)
                visit(st.body)
            elif isinstance(st, (ast.If, ast.While)):
                visit(st.body)
                visit(st.orelse)
            elif isinstance(st, ast.Try):
                visit(st.body)
                for h in st.handlers:
                    if h.name:
                        other.add(h.name)
                    visit(h.body)
                visit(st.orelse)
                visit(st.finalbody)

    visit(tree.body)
    for n in ast.walk(tree):
        if isinstance(n, ast.Global):
            other.update(n.names)
    return flags - other


class _Module:
    """The top-level definitions, the imports, and the bool flags of one source file."""

    def __init__(self, tree: ast.Module, rel_path: str, root: str):
        self.defs: Dict[str, Definition] = {}
        self.imports: Dict[str, Tuple[Optional[str], str]] = {}
        self.flags: Set[str] = module_bool_flags(tree)
        for stmt in tree.body:
            if isinstance(stmt, (ast.ClassDef, ast.FunctionDef)):
                self.defs[stmt.name] = stmt
            elif isinstance(stmt, ast.ImportFrom):
                source = _module_file(root, rel_path, stmt.level, stmt.module or "")
                for alias in stmt.names:
                    if alias.name == "*":
                        continue
                    self.imports[alias.asname or alias.name] = (source, alias.name)


def _module_file(root: str, from_rel: str, level: int, module: str) -> Optional[str]:
    """The repository-relative file a `from ... import` names, or None if it is not in the repository."""
    parts = module.split(".") if module else []
    if level > 0:
        base = os.path.dirname(from_rel)
        for _ in range(level - 1):
            base = os.path.dirname(base)
        candidates = [os.path.join(base, *parts)]
    else:
        candidates = [os.path.join(*parts), os.path.join("src", *parts)] if parts else []
    for candidate in candidates:
        for rel in (candidate + ".py", os.path.join(candidate, "__init__.py")):
            if os.path.isfile(os.path.join(root, rel)):
                return os.path.normpath(rel)
    return None


class ProjectScope:
    """Resolves the classes and functions a source file can name.

    `class_def(name)` and `function_def(name)` return the definition node, or None
    when the name is not defined in the file or cannot be followed to a definition
    inside the repository.
    """

    def __init__(self, root: str, rel_path: str):
        self.root = os.path.abspath(root)
        self.rel_path = os.path.normpath(rel_path)
        self._modules: Dict[str, Optional[_Module]] = {}
        self._classes: Optional[List[ast.ClassDef]] = None
        if self._load(self.rel_path) is None:
            raise FileNotFoundError(f"{rel_path} is not a readable Python file under {root}")

    def _load(self, rel: str) -> Optional[_Module]:
        if rel not in self._modules:
            self._modules[rel] = None  # guards against import cycles while loading
            try:
                with open(os.path.join(self.root, rel), encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=rel)
            except (OSError, SyntaxError, UnicodeDecodeError):
                return None
            self._modules[rel] = _Module(tree, rel, self.root)
        return self._modules[rel]

    def _lookup(self, rel: str, name: str, want: type, hops: int) -> Optional[Definition]:
        module = self._load(rel) if rel is not None and hops <= _MAX_HOPS else None
        if module is None:
            return None
        node = module.defs.get(name)
        if isinstance(node, want):
            return node
        if node is None and name in module.imports:
            source, original = module.imports[name]
            return self._lookup(source, original, want, hops + 1)
        return None

    def _repo_classes(self) -> List[ast.ClassDef]:
        """Every class defined in a Python file of the repository, read once."""
        if self._classes is None:
            self._classes = []
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if d != ".git"]
                for filename in filenames:
                    if not filename.endswith(".py"):
                        continue
                    try:
                        with open(os.path.join(dirpath, filename), encoding="utf-8") as fh:
                            tree = ast.parse(fh.read(), filename=filename)
                    except (OSError, SyntaxError, UnicodeDecodeError):
                        continue
                    self._classes.extend(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        return self._classes

    def is_module_flag(self, name: str) -> bool:
        """True if the file binds `name` only to True or False (see module_bool_flags)."""
        module = self._load(self.rel_path)
        return module is not None and name in module.flags

    def subclass_members(self, classdef: ast.ClassDef) -> Set[str]:
        """The names a subclass of `classdef` anywhere in the repository defines (see subclass_members)."""
        return subclass_members(self._repo_classes(), classdef.name)

    def class_def(self, name: str) -> Optional[ast.ClassDef]:
        return self._lookup(self.rel_path, name, ast.ClassDef, 0)  # type: ignore[return-value]

    def function_def(self, name: str) -> Optional[ast.FunctionDef]:
        return self._lookup(self.rel_path, name, ast.FunctionDef, 0)  # type: ignore[return-value]


__all__ = ["ProjectScope", "module_bool_flags"]
