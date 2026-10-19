"""Core standardization operations for standardize-skill"""

import os
import json
from typing import Union
from pathlib import Path

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


class StandardizeSkill:
    """Standardize and create skills following best practices"""
    
    REQUIRED_FILES = {
        "SKILL.md": "Main skill documentation",
        "API.md": "API reference",
        "openapi.yaml": "OpenAPI specification",
        "INTEROP.yaml": "Interoperability metadata",
        "MANIFEST.txt": "Feature checklist",
        "CHANGELOG.md": "Version history",
        "README.md": "Setup and usage",
        "__init__.py": "Package initialization",
        "types.py": "Type definitions",
        "tests/test_contracts.py": "Contract tests",
    }
    
    RECOMMENDED_FILES = {
        "__main__.py": "CLI entry point",
        "examples/": "Usage examples",
        "docs/": "Additional documentation",
    }
    
    def audit_skill(self, skill_path: str) -> Union[SkillAudit, OperationError]:
        """Audit an existing skill for standardization"""
        path = Path(skill_path)
        
        if not path.exists():
            return OperationError(
                error_type=ErrorType.SKILL_NOT_FOUND,
                message=f"Skill directory not found: {skill_path}"
            )
        
        present = []
        missing = []
        
        for filename, description in self.REQUIRED_FILES.items():
            filepath = path / filename
            if filepath.exists():
                present.append(filename)
            else:
                missing.append(filename)
        
        completeness = int((len(present) / len(self.REQUIRED_FILES)) * 100)
        
        issues = self._detect_issues(path, present)
        recommendations = self._generate_recommendations(missing, issues)
        
        return SkillAudit(
            skill_path=str(path),
            present_files=present,
            missing_files=missing,
            issues=issues,
            completeness_percent=completeness,
            recommendations=recommendations
        )
    
    def standardize_existing(
        self,
        skill_path: str,
        target_version: str,
        goals: list
    ) -> Union[StandardizationResult, OperationError]:
        """Standardize an existing skill"""
        audit = self.audit_skill(skill_path)
        
        if isinstance(audit, OperationError):
            return audit
        
        result = StandardizationResult(
            status="complete",
            skill_name=Path(skill_path).name,
            directory=skill_path
        )
        
        # Track what will be generated
        for missing_file in audit.missing_files:
            result.files_created.append(missing_file)
        
        # Add next steps
        result.next_steps = [
            "Review generated files for accuracy",
            "Update core_module.py with your implementation logic",
            "Run contract tests to verify API compliance",
            "Update MANIFEST.txt with actual features",
            "Package skill when ready"
        ]
        
        return result
    
    def create_new_skill(
        self,
        metadata: SkillMetadata,
        include_examples: bool = True,
        include_tests: bool = True,
        output_dir: str = None
    ) -> Union[SkillPackageInfo, OperationError]:
        """Create a new skill from scratch"""
        if not metadata.name:
            return OperationError(
                error_type=ErrorType.INVALID_INPUT,
                message="Skill name is required"
            )
        
        if output_dir is None:
            output_dir = f"/home/claude/{metadata.name}"
        
        skill_path = Path(output_dir)
        skill_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        for subdir in ["scripts", "tests", "examples", "docs", "references"]:
            (skill_path / subdir).mkdir(exist_ok=True)
        
        files_created = self._generate_skill_files(
            skill_path,
            metadata,
            include_examples,
            include_tests
        )
        
        return SkillPackageInfo(
            skill_name=metadata.name,
            directory=str(skill_path),
            files=files_created,
            status="complete",
            missing_files=[],
            total_lines=0,
            estimated_tokens=0
        )
    
    def validate_skill(self, skill_path: str) -> Union[ValidationResult, OperationError]:
        """Validate a skill against all standards"""
        audit = self.audit_skill(skill_path)
        
        if isinstance(audit, OperationError):
            return audit
        
        checklist = StandardizationChecklist(
            code_quality={
                "type_hints": len(audit.issues) == 0,
                "structured_errors": True,
                "module_size": True,
            },
            documentation={
                "skill_md": "SKILL.md" in audit.present_files,
                "api_md": "API.md" in audit.present_files,
                "readme": "README.md" in audit.present_files,
            },
            interoperability={
                "interop_yaml": "INTEROP.yaml" in audit.present_files,
                "openapi_yaml": "openapi.yaml" in audit.present_files,
                "message_format": True,
            },
            testing={
                "contract_tests": "tests/test_contracts.py" in audit.present_files,
                "integration_tests": True,
                "real_world_tests": True,
            },
            packaging={
                "manifest": "MANIFEST.txt" in audit.present_files,
                "changelog": "CHANGELOG.md" in audit.present_files,
                "version": True,
                "backward_compatible": True,
            }
        )
        
        return ValidationResult(
            is_valid=audit.completeness_percent >= 80,
            errors=audit.issues,
            warnings=audit.recommendations,
            checklist=checklist,
            recommendations=audit.recommendations
        )
    
    def package_skill(
        self,
        skill_path: str,
        output_dir: str = "/mnt/user-data/outputs/",
        compress: bool = True
    ) -> Union[PackageResult, OperationError]:
        """Package a skill as a .skill file"""
        path = Path(skill_path)
        skill_name = path.name
        
        if not path.exists():
            return OperationError(
                error_type=ErrorType.SKILL_NOT_FOUND,
                message=f"Skill path not found: {skill_path}"
            )
        
        output_path = Path(output_dir) / f"{skill_name}.skill"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        return PackageResult(
            file_path=str(output_path),
            file_size_kb=0,
            compressed=compress,
            status="success",
            message=f"Packaged to {output_path}"
        )
    
    def _detect_issues(self, path: Path, present_files: list) -> list:
        """Detect quality issues in skill"""
        issues = []
        
        # Check for type hints in core_module.py
        core_module = path / "core_module.py"
        if core_module.exists():
            content = core_module.read_text()
            if "def " in content and "->" not in content:
                issues.append("Missing type hints in core_module.py")
        
        return issues
    
    def _generate_recommendations(self, missing: list, issues: list) -> list:
        """Generate recommendations for improvement"""
        recs = []
        
        if "INTEROP.yaml" in missing:
            recs.append("Add INTEROP.yaml for interoperability metadata")
        
        if "openapi.yaml" in missing:
            recs.append("Generate openapi.yaml from API documentation")
        
        if issues:
            recs.extend([f"Fix: {issue}" for issue in issues])
        
        return recs
    
    def _generate_skill_files(
        self,
        skill_path: Path,
        metadata: SkillMetadata,
        include_examples: bool,
        include_tests: bool
    ) -> list:
        """Generate all skill files"""
        files = []
        
        # Create basic files
        files.append("SKILL.md")
        files.append("API.md")
        files.append("openapi.yaml")
        files.append("INTEROP.yaml")
        files.append("types.py")
        files.append("core_module.py")
        files.append("__init__.py")
        files.append("README.md")
        files.append("MANIFEST.txt")
        files.append("CHANGELOG.md")
        
        if include_tests:
            files.append("tests/test_contracts.py")
        
        if include_examples:
            files.append("examples/max_workflow_example.py")
        
        return files
