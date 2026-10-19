"""Data structures for GitHub project analysis."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from pathlib import Path


@dataclass
class LanguageDetection:
    """Results of language detection."""
    primary_language: str
    detected_languages: List[str]
    file_counts: Dict[str, int]
    confidence: float


@dataclass
class FunctionInfo:
    """Details about a function in source code."""
    name: str
    file: str
    start_line: int
    end_line: int
    lines: int
    complexity: int
    is_public: bool
    has_docstring: bool
    imports_external: bool
    has_side_effects: bool
    docstring: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    return_type: Optional[str] = None


@dataclass
class FileInfo:
    """Information about a single source file."""
    path: Path
    language: str
    lines_of_code: int
    functions: List[str] = field(default_factory=list)  # Public function names
    imports: List[str] = field(default_factory=list)    # What this file imports
    exports: List[str] = field(default_factory=list)    # What this file exports
    has_external_calls: bool = False


@dataclass
class CallChain:
    """A chain of function calls across files."""
    chain: List[tuple]  # [(file, function), (file, function), ...]
    depth: int
    has_external_calls: bool


@dataclass
class TokenCostEstimate:
    """Estimated token cost for verification."""
    total_functions: int
    per_function_estimate: int = 150
    total_estimated: int = 0
    per_phase: List[int] = field(default_factory=list)
    estimated_duration_seconds: int = 0
    
    def __post_init__(self):
        """Calculate totals."""
        if not self.per_phase:
            self.per_phase = [
                int(self.total_functions * self.per_function_estimate * 0.25),  # Phase 1
                int(self.total_functions * self.per_function_estimate * 0.35),  # Phase 2
                int(self.total_functions * self.per_function_estimate * 0.25),  # Phase 3
                int(self.total_functions * self.per_function_estimate * 0.15),  # Phase 4
            ]
        if not self.total_estimated:
            self.total_estimated = sum(self.per_phase)
        if not self.estimated_duration_seconds:
            self.estimated_duration_seconds = int(self.total_estimated / 100)


@dataclass
class TestTarget:
    """A function suitable for verification."""
    file: str
    function_name: str
    lines_of_code: int
    cyclomatic_complexity: int
    imports_external_services: bool
    has_side_effects: bool
    has_test_cases: bool
    priority: int = 0  # 0=high, 1=medium, 2=low
    test_examples: Optional[List[Dict]] = None
    verification_difficulty: str = "medium"  # easy, medium, hard
    score: int = 0


@dataclass
class GitHubProject:
    """Represents a cloned GitHub project."""
    repo_name: str
    repo_url: str
    local_path: Path
    primary_language: str
    total_files: int
    total_lines: int
    functions_found: int
    has_tests: bool = False
    test_dirs: List[str] = field(default_factory=list)
    has_setup: bool = False
    config_files: List[str] = field(default_factory=list)


@dataclass
class ProjectStructure:
    """Complete analysis of a project."""
    project: GitHubProject
    files: Dict[str, FileInfo]  # path → FileInfo
    functions: Dict[str, FunctionInfo]  # "file.func" → FunctionInfo
    dependency_graph: Dict[str, List[str]] = field(default_factory=dict)
    circular_imports: List[List[str]] = field(default_factory=list)
    modules: Dict[str, List[Path]] = field(default_factory=dict)
    test_targets: List[TestTarget] = field(default_factory=list)
    estimated_cost: Optional[TokenCostEstimate] = None
