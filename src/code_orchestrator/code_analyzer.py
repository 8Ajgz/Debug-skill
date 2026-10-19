"""Code structure analyzer for extracting functions, call graphs, and complexity metrics."""

import ast
from typing import Dict, List, Optional, Set

from .type_stubs import CodeStructure, Function, OperationError, OperationErrorType


class CodeAnalyzer:
    """Analyzes Python code structure using AST parsing."""

    def __init__(self) -> None:
        """Initialize the analyzer."""
        self.functions: List[Function] = []
        self.call_graph: Dict[str, List[str]] = {}
        self.dependency_graph: Dict[str, List[str]] = {}
        self.modules: Dict[str, List[str]] = {}
        self.current_module: str = "main"

    def extract_from_source(
        self, source_code: str, language: str = "python", module_name: str = "main"
    ) -> tuple[Optional[CodeStructure], Optional[OperationError]]:
        """Extract code structure from source code.
        
        Args:
            source_code: Source code to analyze
            language: Programming language (default: "python")
            module_name: Name of the module (default: "main")
            
        Returns:
            Tuple of (CodeStructure, None) on success or (None, OperationError) on failure
        """
        if language != "python":
            return None, OperationError(
                error_type=OperationErrorType.UNSUPPORTED_LANGUAGE,
                message=f"Language '{language}' not supported in Phase 1 (Python only)",
                context={"language": language}
            )

        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return None, OperationError(
                error_type=OperationErrorType.INVALID_CODE,
                message=f"Syntax error: {str(e)}",
                context={"line": str(e.lineno), "offset": str(e.offset)}
            )

        self.current_module = module_name
        self.functions = []
        self.call_graph = {}
        self.dependency_graph = {}
        self.modules = {module_name: []}

        # First pass: extract all functions
        self._extract_functions(tree, source_code)

        # Second pass: build call graph and dependency graph
        self._build_graphs(tree)

        # Compute complexity scores
        self._compute_complexity_scores(tree)

        # Calculate metrics
        total_lines = len(source_code.splitlines())
        analyzable_lines = sum(f.lines_of_code for f in self.functions)
        analyzable_percentage = (analyzable_lines / total_lines * 100) if total_lines > 0 else 0.0

        structure = CodeStructure(
            functions=self.functions,
            call_graph=self.call_graph,
            dependency_graph=self.dependency_graph,
            modules=self.modules,
            total_lines=total_lines,
            analyzable_percentage=analyzable_percentage,
            language=language
        )

        return structure, None

    def _extract_functions(self, tree: ast.AST, source_code: str) -> None:
        """Extract function definitions from AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Skip private/internal functions
                if node.name.startswith("_"):
                    continue

                # Calculate lines of code
                start_line = node.lineno
                end_line = node.end_lineno or (start_line + 1)
                lines_of_code = end_line - start_line + 1

                # Extract docstring
                docstring = ast.get_docstring(node)

                # Create Function object
                func = Function(
                    name=node.name,
                    module=self.current_module,
                    lines_of_code=lines_of_code,
                    complexity_score=1.0,  # Will be computed later
                    is_testable=True,
                    is_verifiable=True,
                    docstring=docstring
                )

                self.functions.append(func)
                if self.current_module not in self.modules:
                    self.modules[self.current_module] = []
                self.modules[self.current_module].append(func.name)

                # Initialize call graph entry
                self.call_graph[func.name] = []
                self.dependency_graph[func.name] = []

    def _build_graphs(self, tree: ast.AST) -> None:
        """Build call graph and dependency graph."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                calls = self._extract_function_calls(node)
                self.call_graph[node.name] = list(calls)

    def _extract_function_calls(self, func_node: ast.FunctionDef) -> Set[str]:
        """Extract all function calls within a function."""
        calls: Set[str] = set()

        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    # Direct function call: func()
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    # Method call: obj.method() - extract method name
                    if isinstance(node.func.value, ast.Name):
                        calls.add(node.func.attr)

        # Build dependency graph (reverse of call graph)
        for callee in calls:
            if callee in self.dependency_graph:
                if func_node.name not in self.dependency_graph[callee]:
                    self.dependency_graph[callee].append(func_node.name)

        return calls

    def _compute_complexity_scores(self, tree: ast.AST) -> None:
        """Compute cyclomatic complexity for each function."""
        func_by_name = {f.name: f for f in self.functions}

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                if node.name in func_by_name:
                    complexity = self._calculate_cyclomatic_complexity(node)
                    func_by_name[node.name].complexity_score = float(complexity)

    def _calculate_cyclomatic_complexity(self, func_node: ast.FunctionDef) -> int:
        """Calculate cyclomatic complexity (number of decision points + 1)."""
        complexity = 1
        for node in ast.walk(func_node):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                # 'and' and 'or' operators add to complexity
                if isinstance(node, ast.BoolOp) and len(node.values) > 1:
                    complexity += len(node.values) - 1

        return complexity

    def build_call_graph(self) -> Dict[str, List[str]]:
        """Return the call graph."""
        return self.call_graph.copy()

    def build_dependency_graph(self) -> Dict[str, List[str]]:
        """Return the dependency graph (reverse of call graph)."""
        return self.dependency_graph.copy()

    def compute_complexity(self, function_name: str) -> Optional[float]:
        """Get complexity score for a specific function."""
        for func in self.functions:
            if func.name == function_name:
                return func.complexity_score
        return None
