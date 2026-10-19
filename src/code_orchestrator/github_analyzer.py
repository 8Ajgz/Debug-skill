"""GitHub project analyzer: clone and analyze repositories."""

import re
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

from .project_structure import (
    GitHubProject, LanguageDetection, TokenCostEstimate
)


@dataclass
class GitCloneError(Exception):
    """Error cloning GitHub repository."""
    url: str
    reason: str


@dataclass
class InvalidGitHubURL(Exception):
    """Invalid GitHub URL format."""
    url: str


class GitHubProjectAnalyzer:
    """Analyze GitHub projects for verification."""
    
    SUPPORTED_LANGUAGES = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".java": "Java",
        ".go": "Go",
        ".rs": "Rust",
        ".cpp": "C++",
        ".c": "C",
    }
    
    LANGUAGE_EXTENSIONS = {
        "Python": [".py"],
        "JavaScript": [".js", ".jsx"],
        "TypeScript": [".ts", ".tsx"],
        "Java": [".java"],
        "Go": [".go"],
        "Rust": [".rs"],
        "C++": [".cpp", ".cc", ".cxx", ".h", ".hpp"],
        "C": [".c", ".h"],
    }
    
    TEST_DIR_PATTERNS = [
        "tests",
        "test",
        "spec",
        "specs",
        "__tests__",
        ".tests",
    ]
    
    def __init__(self, base_dir: Path = None):
        """Initialize analyzer.
        
        Args:
            base_dir: Base directory for cloning projects (default: temp directory)
        """
        if base_dir is None:
            import tempfile
            base_dir = Path(tempfile.gettempdir()) / "code-orchestrator" / "github-projects"
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def analyze_github_project(self, github_url: str) -> GitHubProject:
        """
        Main entry point: clone and analyze GitHub project.
        
        Args:
            github_url: Full GitHub URL (https://github.com/user/repo)
            
        Returns:
            GitHubProject with metadata
            
        Raises:
            InvalidGitHubURL: If URL is invalid
            GitCloneError: If clone fails
        """
        self.validate_github_url(github_url)
        
        # Extract repo name from URL
        repo_name = github_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        
        # Clone to local directory
        local_path = self.base_dir / repo_name
        if local_path.exists():
            shutil.rmtree(local_path)
        
        self.clone_github_repo(github_url, local_path)
        
        # Analyze structure
        detection = self.detect_languages(local_path)
        metadata = self.get_project_metadata(local_path)
        
        # Count files and functions
        total_files = len(list(local_path.rglob("*")))
        total_lines = self._count_lines(local_path)
        functions_found = self._count_functions(local_path)
        
        project = GitHubProject(
            repo_name=repo_name,
            repo_url=github_url,
            local_path=local_path,
            primary_language=detection.primary_language,
            total_files=total_files,
            total_lines=total_lines,
            functions_found=functions_found,
            has_tests=metadata.get("has_tests", False),
            test_dirs=metadata.get("test_dirs", []),
            has_setup=metadata.get("has_setup", False),
            config_files=metadata.get("config_files", []),
        )
        
        return project
    
    def validate_github_url(self, url: str) -> bool:
        """
        Validate GitHub URL format.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid
            
        Raises:
            InvalidGitHubURL: If invalid
        """
        pattern = r"https?://(www\.)?github\.com/[a-zA-Z0-9\-_.]+/[a-zA-Z0-9\-_.]+(/\.git)?/?$"
        if not re.match(pattern, url):
            raise InvalidGitHubURL(url)
        return True
    
    def clone_github_repo(self, github_url: str, target_dir: Path) -> Path:
        """
        Clone GitHub repository using shallow clone.
        
        Args:
            github_url: Repository URL
            target_dir: Local directory to clone into
            
        Returns:
            Path to cloned repository
            
        Raises:
            GitCloneError: If clone fails
        """
        try:
            # Shallow clone for speed
            subprocess.run(
                ["git", "clone", "--depth=1", github_url, str(target_dir)],
                capture_output=True,
                timeout=300,  # 5 min timeout
                check=True,
            )
            return target_dir
        except subprocess.TimeoutExpired:
            raise GitCloneError(github_url, "Clone timed out (>5 minutes)")
        except subprocess.CalledProcessError as e:
            raise GitCloneError(github_url, str(e.stderr))
        except FileNotFoundError:
            raise GitCloneError(github_url, "git command not found")
    
    def detect_languages(self, repo_path: Path) -> LanguageDetection:
        """
        Detect programming languages in repository.
        
        Args:
            repo_path: Path to cloned repository
            
        Returns:
            LanguageDetection with file counts
        """
        file_counts: Dict[str, int] = {}
        
        # Count files by extension
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                ext = file_path.suffix
                if ext in self.SUPPORTED_LANGUAGES:
                    lang = self.SUPPORTED_LANGUAGES[ext]
                    file_counts[lang] = file_counts.get(lang, 0) + 1
        
        # Determine primary language
        primary_language = "Unknown"
        if file_counts:
            primary_language = max(file_counts, key=file_counts.get)
        
        detected_languages = list(file_counts.keys())
        confidence = min(1.0, len(file_counts) / 5) if file_counts else 0.0
        
        # Convert to file extension counts for detailed report
        ext_counts = {f".{ext}": count for ext, count in file_counts.items()}
        
        return LanguageDetection(
            primary_language=primary_language,
            detected_languages=detected_languages,
            file_counts=ext_counts,
            confidence=confidence,
        )
    
    def get_project_metadata(self, repo_path: Path) -> Dict[str, any]:
        """
        Extract project metadata.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Dictionary with metadata
        """
        metadata = {
            "has_tests": False,
            "test_dirs": [],
            "has_setup": False,
            "config_files": [],
        }
        
        # Find test directories
        for test_dir in self.TEST_DIR_PATTERNS:
            test_path = repo_path / test_dir
            if test_path.exists() and test_path.is_dir():
                metadata["has_tests"] = True
                metadata["test_dirs"].append(test_dir)
        
        # Find setup/config files
        config_patterns = [
            "setup.py", "setup.cfg", "pyproject.toml", "requirements.txt",
            "package.json", "package-lock.json", "yarn.lock",
            "Makefile", "Dockerfile", "docker-compose.yml",
            "tox.ini", ".travis.yml", ".github",
        ]
        
        for pattern in config_patterns:
            if (repo_path / pattern).exists():
                metadata["config_files"].append(pattern)
                if pattern in ["setup.py", "package.json", "Makefile"]:
                    metadata["has_setup"] = True
        
        return metadata
    
    def estimate_verification_cost(self, project: GitHubProject) -> TokenCostEstimate:
        """
        Estimate tokens needed to verify project.
        
        Args:
            project: GitHubProject
            
        Returns:
            TokenCostEstimate
        """
        # Estimate functions to verify (typically 5-20)
        target_functions = min(20, max(5, int(project.functions_found * 0.1)))
        
        estimate = TokenCostEstimate(
            total_functions=target_functions,
            per_function_estimate=150,
        )
        
        return estimate
    
    def _count_lines(self, repo_path: Path) -> int:
        """Count total lines of code."""
        total = 0
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and file_path.suffix in self.SUPPORTED_LANGUAGES:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        total += len(f.readlines())
                except Exception:
                    pass
        return total
    
    def _count_functions(self, repo_path: Path) -> int:
        """Count functions in Python files (simple heuristic)."""
        count = 0
        for file_path in repo_path.rglob("*.py"):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.strip().startswith("def "):
                            count += 1
            except Exception:
                pass
        return count
