"""CLI entry point for standardize-skill"""

import sys
import argparse
from pathlib import Path

from standardize_skill import StandardizeSkill, SkillMetadata, SkillAudit, ValidationResult


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Standardize and create skills following best practices"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # audit subcommand
    audit_parser = subparsers.add_parser("audit", help="Audit an existing skill")
    audit_parser.add_argument("skill_path", help="Path to skill directory")
    
    # standardize subcommand
    standardize_parser = subparsers.add_parser("standardize", help="Standardize an existing skill")
    standardize_parser.add_argument("skill_path", help="Path to skill directory")
    standardize_parser.add_argument("--version", default="2.0.0", help="Target version")
    standardize_parser.add_argument("--goals", nargs="+", default=["add_all"], help="Standardization goals")
    
    # validate subcommand
    validate_parser = subparsers.add_parser("validate", help="Validate a skill")
    validate_parser.add_argument("skill_path", help="Path to skill directory")
    
    # package subcommand
    package_parser = subparsers.add_parser("package", help="Package a skill")
    package_parser.add_argument("skill_path", help="Path to skill directory")
    package_parser.add_argument("--output", default="/mnt/user-data/outputs/", help="Output directory")
    package_parser.add_argument("--no-compress", action="store_true", help="Don't compress")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    standardizer = StandardizeSkill()
    
    if args.command == "audit":
        result = standardizer.audit_skill(args.skill_path)
        
        if isinstance(result, SkillAudit):
            print(f"✅ Audit Results for {result.skill_path}")
            print(f"   Completeness: {result.completeness_percent}%")
            print(f"   Present files: {len(result.present_files)}")
            print(f"   Missing files: {len(result.missing_files)}")
            
            if result.missing_files:
                print(f"\n   Missing:")
                for f in result.missing_files:
                    print(f"     - {f}")
            
            if result.issues:
                print(f"\n   Issues:")
                for issue in result.issues:
                    print(f"     - {issue}")
            
            if result.recommendations:
                print(f"\n   Recommendations:")
                for rec in result.recommendations:
                    print(f"     - {rec}")
        else:
            print(f"❌ Error: {result.message}")
            return 1
    
    elif args.command == "standardize":
        result = standardizer.standardize_existing(
            args.skill_path,
            args.version,
            args.goals
        )
        
        print(f"✅ Standardization Status: {result.status}")
        print(f"   Skill: {result.skill_name}")
        print(f"   Directory: {result.directory}")
        
        if result.files_created:
            print(f"\n   Files created ({len(result.files_created)}):")
            for f in result.files_created:
                print(f"     + {f}")
        
        if result.next_steps:
            print(f"\n   Next steps:")
            for i, step in enumerate(result.next_steps, 1):
                print(f"     {i}. {step}")
    
    elif args.command == "validate":
        result = standardizer.validate_skill(args.skill_path)
        
        if isinstance(result, ValidationResult):
            print(f"✅ Validation Report")
            print(f"   Valid: {result.is_valid}")
            print(f"   Completeness: {result.checklist.completion_percent}%")
            
            if result.errors:
                print(f"\n   Errors:")
                for error in result.errors:
                    print(f"     - {error}")
            
            if result.warnings:
                print(f"\n   Warnings:")
                for warning in result.warnings:
                    print(f"     - {warning}")
            
            if result.recommendations:
                print(f"\n   Recommendations:")
                for rec in result.recommendations:
                    print(f"     - {rec}")
        else:
            print(f"❌ Error: {result.message}")
            return 1
    
    elif args.command == "package":
        result = standardizer.package_skill(
            args.skill_path,
            args.output,
            compress=not args.no_compress
        )
        
        if result.status == "success":
            print(f"✅ Packaged successfully!")
            print(f"   File: {result.file_path}")
            print(f"   Size: {result.file_size_kb} KB")
        else:
            print(f"❌ Packaging failed: {result.message}")
            return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
