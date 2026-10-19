"""Type definitions for standardize-skill"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class ErrorType(Enum):
    """Error types for standardize-skill operations"""
    INVALID_INPUT = "invalid_input"
    SKILL_NOT_FOUND = "skill_not_found"
    MISSING_REQUIRED_FILES = "missing_required_files"
    VALIDATION_FAILED = "validation_failed"
    FILE_GENERATION_FAILED = "file_generation_failed"
    DEPENDENCY_FAILURE = "dependency_failure"


@dataclass
class SkillMetadata:
    """Metadata for defining a new skill"""
    name: str
    version: str
    description: str
    use_cases: List[str]
    primary_function: str
    operations: List[Dict[str, Any]]
    compatibility: str = "Python 3.8+"
    dependencies: List[str] = field(default_factory=list)


@dataclass
class SkillAudit:
    """Results from auditing an existing skill"""
    skill_path: str
    present_files: List[str]
    missing_files: List[str]
    issues: List[str]
    completeness_percent: int
    recommendations: List[str]


@dataclass
class StandardizationChecklist:
    """Standardization checklist for skill package"""
    code_quality: Dict[str, bool]
    documentation: Dict[str, bool]
    interoperability: Dict[str, bool]
    testing: Dict[str, bool]
    packaging: Dict[str, bool]
    
    @property
    def total_items(self) -> int:
        """Total items in checklist"""
        return sum(len(v) for v in [
            self.code_quality, self.documentation,
            self.interoperability, self.testing, self.packaging
        ])
    
    @property
    def completed_items(self) -> int:
        """Items marked complete"""
        return sum(sum(v.values()) for v in [
            self.code_quality, self.documentation,
            self.interoperability, self.testing, self.packaging
        ])
    
    @property
    def completion_percent(self) -> int:
        """Completion percentage"""
        if self.total_items == 0:
            return 100
        return int((self.completed_items / self.total_items) * 100)


@dataclass
class UpgradeReport:
    """Report from standardizing an existing skill"""
    skill_name: str
    version_from: str
    version_to: str
    files_created: List[str]
    files_updated: List[str]
    files_needing_review: List[str]
    issues_found: List[str]
    status: str  # "complete", "needs_review", "failed"
    checklist: StandardizationChecklist
    next_steps: List[str]


@dataclass
class SkillPackageInfo:
    """Info about a generated skill package"""
    skill_name: str
    directory: str
    files: List[str]
    status: str  # "complete", "draft", "incomplete"
    missing_files: List[str]
    total_lines: int
    estimated_tokens: int


@dataclass
class OperationError:
    """Structured error response (never raise, always return)"""
    error_type: ErrorType
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class ValidationResult:
    """Result of validating a skill against standards"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    checklist: StandardizationChecklist
    recommendations: List[str]


@dataclass
class PackageResult:
    """Result of packaging a skill"""
    file_path: str
    file_size_kb: int
    compressed: bool
    status: str  # "success", "failed"
    message: str


@dataclass
class StandardizationResult:
    """Result of any standardization operation"""
    status: str  # "complete", "needs_review", "failed"
    skill_name: Optional[str]
    directory: Optional[str]
    files_created: List[str] = field(default_factory=list)
    files_updated: List[str] = field(default_factory=list)
    error: Optional[OperationError] = None
    checklist: Optional[StandardizationChecklist] = None
    next_steps: List[str] = field(default_factory=list)
