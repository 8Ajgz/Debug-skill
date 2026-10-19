"""Test target extractor: identify suitable functions for verification."""

import ast
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from .project_structure import TestTarget, FunctionInfo, GitHubProject


class TestTargetExtractor:
    """Extract suitable verification targets from project."""
    
    def __init__(self):
        """Initialize extractor."""
        self.max_reasonable_complexity = 50
        self.min_reasonable_complexity = 3
    
    def extract_test_targets(self, repo_path: Path, 
                            project: GitHubProject,
                            target_count: int = 10) -> List[TestTarget]:
        """
        Find representative functions to verify.
        
        Args:
            repo_path: Path to repository
            project: GitHubProject metadata
            target_count: Desired number of targets (5-20)
            
        Returns:
            Sorted list of TestTarget objects (best first)
        """
        candidates: List[Tuple[TestTarget, int]] = []  # (target, score)
        
        # Scan all Python files
        for py_file in repo_path.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            
            try:
                with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                    source = f.read()
            except Exception:
                continue
            
            # Extract functions
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                    # Analyze function
                    func_info = self._analyze_function(
                        node, py_file, source, repo_path
                    )
                    
                    target, score = self._create_test_target(func_info)
                    if target and score > 0:
                        candidates.append((target, score))
        
        # Sort by score (best first) and take top N
        candidates.sort(key=lambda x: x[1], reverse=True)
        targets = [target for target, _ in candidates[:target_count]]
        
        # Set priority based on position
        for i, target in enumerate(targets):
            if i < len(targets) / 3:
                target.priority = 0  # High
            elif i < 2 * len(targets) / 3:
                target.priority = 1  # Medium
            else:
                target.priority = 2  # Low
        
        return targets
    
    def _analyze_function(self, func_node: ast.FunctionDef, 
                         file_path: Path, source: str,
                         repo_path: Path) -> FunctionInfo:
        """
        Analyze a function AST node.
        
        Args:
            func_node: AST FunctionDef node
            file_path: Path to file
            source: Source code
            repo_path: Repository root
            
        Returns:
            FunctionInfo object
        """
        rel_path = str(file_path.relative_to(repo_path))
        
        # Extract docstring
        docstring = ast.get_docstring(func_node)
        
        # Count lines
        start_line = func_node.lineno
        end_line = func_node.end_lineno or start_line
        lines = end_line - start_line + 1
        
        # Extract parameters
        parameters = [arg.arg for arg in func_node.args.args]
        
        # Calculate complexity (simple heuristic)
        complexity = self._calculate_complexity(func_node)
        
        # Check for external calls
        imports_external = self._check_external_calls(source, start_line, end_line)
        
        # Check for side effects
        has_side_effects = self._check_side_effects(func_node)
        
        # Check return type annotation
        return_type = None
        if func_node.returns:
            try:
                return_type = ast.unparse(func_node.returns)
            except Exception:
                pass
        
        return FunctionInfo(
            name=func_node.name,
            file=rel_path,
            start_line=start_line,
            end_line=end_line,
            lines=lines,
            complexity=complexity,
            is_public=not func_node.name.startswith("_"),
            has_docstring=docstring is not None,
            imports_external=imports_external,
            has_side_effects=has_side_effects,
            docstring=docstring,
            parameters=parameters,
            return_type=return_type,
        )
    
    def _create_test_target(self, func_info: FunctionInfo) -> Tuple[Optional[TestTarget], int]:
        """
        Create TestTarget from FunctionInfo with scoring.
        
        Returns:
            (TestTarget or None, score)
        """
        # Calculate score (0-100)
        score = 0
        
        # Public function (+20)
        if func_info.is_public:
            score += 20
        
        # Has docstring (+10)
        if func_info.has_docstring:
            score += 10
        
        # Reasonable complexity (+30 if in range)
        if 3 <= func_info.complexity <= 50:
            score += 30
        elif func_info.complexity > 50:
            score -= 10  # Too complex
        elif func_info.complexity < 3:
            score -= 5  # Too simple
        
        # No external calls (+25)
        if not func_info.imports_external:
            score += 25
        else:
            score -= 15
        
        # No side effects (+15)
        if not func_info.has_side_effects:
            score += 15
        else:
            score -= 10
        
        # Has parameters (+10)
        if func_info.parameters:
            score += 10
        
        # Has return type annotation (+10)
        if func_info.return_type:
            score += 10
        
        # Filter: must be public, no external calls, reasonable complexity
        if not func_info.is_public or func_info.imports_external:
            score = max(0, score - 30)
        
        if score <= 0:
            return None, 0
        
        # Determine difficulty
        if func_info.complexity < 5:
            difficulty = "easy"
        elif func_info.complexity < 20:
            difficulty = "medium"
        else:
            difficulty = "hard"
        
        target = TestTarget(
            file=func_info.file,
            function_name=func_info.name,
            lines_of_code=func_info.lines,
            cyclomatic_complexity=func_info.complexity,
            imports_external_services=func_info.imports_external,
            has_side_effects=func_info.has_side_effects,
            has_test_cases=False,  # Would need to check test files
            verification_difficulty=difficulty,
            score=score,
        )
        
        return target, score
    
    @staticmethod
    def _calculate_complexity(func_node: ast.FunctionDef) -> int:
        """
        Calculate cyclomatic complexity (simple heuristic).
        
        Counts branching statements: if, elif, else, for, while, except, etc.
        """
        complexity = 1
        
        for node in ast.walk(func_node):
            if isinstance(node, (ast.If, ast.IfExp)):
                complexity += 1
            elif isinstance(node, (ast.For, ast.While)):
                complexity += 1
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1
            elif isinstance(node, ast.And):
                complexity += 1
            elif isinstance(node, ast.Or):
                complexity += 1
        
        return complexity
    
    @staticmethod
    def _check_external_calls(source: str, start_line: int, 
                             end_line: int) -> bool:
        """Check if function has external service calls."""
        lines = source.split("\n")[start_line-1:end_line]
        func_source = "\n".join(lines)
        
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
            if re.search(pattern, func_source):
                return True
        
        return False
    
    @staticmethod
    def _check_side_effects(func_node: ast.FunctionDef) -> bool:
        """Check if function has side effects (writes, deletes, etc.)."""
        for node in ast.walk(func_node):
            # File operations
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ["open", "write", "delete", "remove", "mkdir"]:
                        return True
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in ["write", "delete", "remove", "append", "save"]:
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
            "/test",
            "/tests",
        ]
        
        path_str = str(file_path)
        return any(pattern in path_str for pattern in skip_patterns)
