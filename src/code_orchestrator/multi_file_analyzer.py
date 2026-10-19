"""Multi-file analyzer: analyze relationships across project files."""

import ast
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict

from .project_structure import FileInfo, CallChain, ProjectStructure


class MultiFileAnalyzer:
    """Analyze relationships across files in a project."""
    
    def analyze_project_structure(self, repo_path: Path) -> Dict[str, FileInfo]:
        """
        Analyze all files in project.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Dictionary mapping file paths to FileInfo objects
        """
        files = {}
        
        for file_path in repo_path.rglob("*.py"):
            if not self._should_skip_file(file_path):
                file_info = self.extract_file_info(file_path)
                rel_path = str(file_path.relative_to(repo_path))
                files[rel_path] = file_info
        
        return files
    
    def extract_file_info(self, file_path: Path) -> FileInfo:
        """
        Extract information from a single file.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            FileInfo object
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()
        except Exception:
            return FileInfo(
                path=file_path,
                language="Python",
                lines_of_code=0,
            )
        
        lines = source.split("\n")
        loc = len(lines)
        
        # Parse AST
        functions = []
        imports = []
        
        try:
            tree = ast.parse(source)
            
            # Extract functions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Only include public functions
                    if not node.name.startswith("_"):
                        functions.append(node.name)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    imports.extend(self._extract_imports(node))
        except SyntaxError:
            pass
        
        # Detect external service calls
        has_external = self._detect_external_calls(source)
        
        return FileInfo(
            path=file_path,
            language="Python",
            lines_of_code=loc,
            functions=functions,
            imports=list(set(imports)),
            exports=functions,
            has_external_calls=has_external,
        )
    
    def build_dependency_graph(self, repo_path: Path) -> Dict[str, List[str]]:
        """
        Build import dependency graph across files.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Dictionary mapping file → list of files it imports from
        """
        files = self.analyze_project_structure(repo_path)
        graph: Dict[str, List[str]] = defaultdict(list)
        
        # Build reverse mapping: module name → file path
        module_map = {}
        for file_path, file_info in files.items():
            module_name = file_path.replace(".py", "").replace("/", ".")
            module_map[module_name] = file_path
        
        # For each file, find what it imports
        for file_path, file_info in files.items():
            for import_name in file_info.imports:
                # Try to resolve import to a file in the project
                if import_name in module_map:
                    graph[file_path].append(module_map[import_name])
        
        return dict(graph)
    
    def find_call_chains(self, repo_path: Path, max_depth: int = 5) -> List[CallChain]:
        """
        Find interesting call chains across files.
        
        Args:
            repo_path: Path to repository
            max_depth: Maximum chain depth
            
        Returns:
            List of CallChain objects
        """
        files = self.analyze_project_structure(repo_path)
        chains = []
        
        # Find entry points (main functions, class methods)
        entry_points = []
        for file_path, file_info in files.items():
            if "main" in file_info.functions:
                entry_points.append((file_path, "main"))
        
        # For each entry point, trace calls (simplified)
        for file_path, func_name in entry_points:
            chain = [(file_path, func_name)]
            chains.append(CallChain(
                chain=chain,
                depth=1,
                has_external_calls=files[file_path].has_external_calls,
            ))
        
        return chains
    
    def identify_circular_imports(self, repo_path: Path) -> List[List[str]]:
        """
        Detect circular imports.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            List of circular import cycles
        """
        dep_graph = self.build_dependency_graph(repo_path)
        cycles = []
        
        def find_cycles_from(node, visited, rec_stack, path):
            """DFS to find cycles."""
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in dep_graph.get(node, []):
                if neighbor not in visited:
                    find_cycles_from(neighbor, visited, rec_stack, path)
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    if cycle not in cycles:
                        cycles.append(cycle)
            
            rec_stack.remove(node)
            path.pop()
        
        visited = set()
        for node in dep_graph:
            if node not in visited:
                find_cycles_from(node, visited, set(), [])
        
        return cycles
    
    def find_module_boundaries(self, repo_path: Path) -> Dict[str, List[Path]]:
        """
        Identify logical modules/packages.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Dictionary mapping module name → list of files
        """
        modules: Dict[str, List[Path]] = defaultdict(list)
        
        for py_file in repo_path.rglob("*.py"):
            if py_file.name == "__init__.py":
                # This defines a module
                module_name = py_file.parent.name
                modules[module_name] = list(py_file.parent.glob("*.py"))
        
        return dict(modules)
    
    @staticmethod
    def _extract_imports(node) -> List[str]:
        """Extract import names from AST node."""
        imports = []
        
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        
        return imports
    
    @staticmethod
    def _detect_external_calls(source: str) -> bool:
        """Detect calls to external services."""
        patterns = [
            r"requests\.",
            r"\.query\(",
            r"\.execute\(",
            r"\.fetch\(",
            r"http\.",
            r"urllib\.",
            r"socket\.",
            r"sqlalchemy",
            r"\.connect\(",
            r"redis\.",
            r"pymongo\.",
        ]
        
        for pattern in patterns:
            if re.search(pattern, source):
                return True
        
        return False
    
    @staticmethod
    def _should_skip_file(file_path: Path) -> bool:
        """Check if file should be skipped."""
        skip_patterns = [
            "__pycache__",
            ".git",
            "venv",
            "env",
            ".egg",
            "build",
            "dist",
        ]
        
        path_str = str(file_path)
        return any(pattern in path_str for pattern in skip_patterns)
