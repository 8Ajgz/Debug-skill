"""standardize-skill: Standardize and create skills following API, packaging, and interoperability guidelines"""

__version__ = "1.0.0"
__version_info__ = (1, 0, 0)

from .core_module import StandardizeSkill
from .skill_types import (
    SkillMetadata,
    SkillAudit,
    SkillPackageInfo,
    OperationError,
    ErrorType,
    StandardizationResult,
    StandardizationChecklist,
    ValidationResult,
    PackageResult,
)

__all__ = [
    "StandardizeSkill",
    "SkillMetadata",
    "SkillAudit",
    "SkillPackageInfo",
    "OperationError",
    "ErrorType",
    "StandardizationResult",
    "StandardizationChecklist",
    "ValidationResult",
    "PackageResult",
]

API_TOKEN_PROFILE = {
    "audit_skill": {
        "sandbox_cost": 0,
        "claude_cost": 0,
        "description": "Pure Python file analysis"
    },
    "standardize_existing": {
        "sandbox_cost": 100,
        "claude_cost": 200,
        "description": "File generation + Claude review of generated templates"
    },
    "create_new_skill": {
        "sandbox_cost": 150,
        "claude_cost": 300,
        "description": "Full skill generation + documentation"
    },
    "validate_skill": {
        "sandbox_cost": 0,
        "claude_cost": 100,
        "description": "Validation and checklist generation"
    },
    "package_skill": {
        "sandbox_cost": 50,
        "claude_cost": 0,
        "description": "Skill packaging and compression"
    }
}
