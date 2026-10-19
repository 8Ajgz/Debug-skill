"""Compatibility shim: types.py -> skill_types.py

This file exists for standardization compliance. The actual type definitions
are in skill_types.py to avoid circular imports with Python's built-in types module.
"""

# Re-export everything from skill_types for backward compatibility
from .skill_types import *  # noqa: F401, F403

__all__ = [
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
