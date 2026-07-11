"""
Phase 2: Rust-Debug Borrow Checker Parser

Parses rustc's JSON output to extract borrow checker violations.
Converts lifetime errors into Variable/Mutation/BugPattern objects.

Requires: rustc (installed via Rust toolchain)

Usage:
    debugger = RustDebugger()
    report = debugger.phase_1_runtime(code)
"""

import json
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..common.interop import (
    UnifiedDebugReport,
    Variable,
    Mutation,
    BugPattern,
    BugSeverity,
    RiskLevel,
    ExecutionEvent,
)


class BorrowCheckerParser:
    """Parse rustc JSON output and extract borrow violations."""
    
    def __init__(self):
        self.rustc_available = self._check_rustc()
    
    def _check_rustc(self) -> bool:
        """Check if rustc is available."""
        try:
            subprocess.run(
                ["rustc", "--version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def parse_borrow_checker_output(self, code: str) -> Dict[str, Any]:
        """
        Compile Rust code and extract borrow checker diagnostics.
        
        Args:
            code: Rust source code
        
        Returns:
            Dict with 'errors', 'warnings', 'timeline'
        """
        if not self.rustc_available:
            return {
                "errors": [],
                "warnings": [],
                "timeline": [],
                "rustc_available": False,
            }
        
        # Write code to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # Run rustc with JSON output
            result = subprocess.run(
                ["rustc", temp_file, "--error-format=json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            # Parse JSON diagnostics
            errors = []
            warnings = []
            timeline = []
            
            for line in result.stderr.split('\n'):
                if not line.strip():
                    continue
                try:
                    diagnostic = json.loads(line)
                    # rustc emits aggregate notes with no code and no spans
                    # (e.g. "aborting due to N previous errors",
                    # "some errors have detailed explanations") — these
                    # aren't diagnostics about a location in the code and
                    # would otherwise show up as a fake unclassified error.
                    if not diagnostic.get('code') and not diagnostic.get('spans'):
                        continue
                    if diagnostic.get('level') == 'error':
                        errors.append(self._parse_diagnostic(diagnostic))
                    elif diagnostic.get('level') == 'warning':
                        warnings.append(self._parse_diagnostic(diagnostic))
                except json.JSONDecodeError:
                    pass
            
            return {
                "errors": errors,
                "warnings": warnings,
                "timeline": timeline,
                "rustc_available": True,
            }
        
        except subprocess.TimeoutExpired:
            return {
                "errors": [{
                    "type": "timeout",
                    "message": "rustc compilation timeout",
                    "line": 1,
                }],
                "warnings": [],
                "timeline": [],
                "rustc_available": True,
            }
        
        except Exception as e:
            return {
                "errors": [{
                    "type": "compilation_error",
                    "message": str(e),
                    "line": 1,
                }],
                "warnings": [],
                "timeline": [],
                "rustc_available": True,
            }
        
        finally:
            # Cleanup
            Path(temp_file).unlink(missing_ok=True)
    
    # rustc error codes that mean "couldn't resolve a name/crate/import" —
    # these fire whenever a file is compiled standalone without its Cargo
    # dependency graph (the normal case for any real-world Rust file pulled
    # out of its crate). They are NOT borrow-checker/ownership violations
    # and must never be reported or risk-classified as such.
    DEPENDENCY_RESOLUTION_CODES = {
        "E0432": "unresolved_import",
        "E0433": "unresolved_crate_or_module",
        "E0405": "trait_not_in_scope",
        "E0412": "type_not_found",
        "E0463": "crate_not_found",
        "E0601": "no_main_function",
    }

    def _parse_diagnostic(self, diagnostic: Dict[str, Any]) -> Dict[str, Any]:
        """Convert rustc diagnostic to standard format.

        Note: diagnostic.get('code') can legitimately be JSON null (rustc
        emits this on several diagnostic kinds, e.g. the trailing "aborting
        due to N previous errors" note), so we must not chain .get() onto
        it directly.
        """
        spans = diagnostic.get('spans', [])
        line = spans[0]['line_start'] if spans else 1

        message = diagnostic.get('message', '')
        code = (diagnostic.get('code') or {}).get('code', '')

        error_type = self._classify_error(message, code)
        category = (
            "dependency_resolution"
            if code in self.DEPENDENCY_RESOLUTION_CODES
            else "borrow_check"
        )

        return {
            "type": error_type,
            "category": category,
            "message": message,
            "code": code,
            "line": line,
            "column": spans[0].get('column_start', 1) if spans else 1,
        }

    def _classify_error(self, message: str, code: str) -> str:
        """Classify borrow checker error type."""
        if code in self.DEPENDENCY_RESOLUTION_CODES:
            return self.DEPENDENCY_RESOLUTION_CODES[code]

        msg_lower = message.lower()

        if "cannot borrow" in msg_lower:
            if "as mutable" in msg_lower:
                return "double_borrow_mut"
            return "borrow_conflict"

        if "use of moved value" in msg_lower:
            return "use_after_move"

        if "does not live long enough" in msg_lower:
            return "lifetime_mismatch"

        if "cannot move" in msg_lower:
            return "move_violation"

        if "multiple mutable" in msg_lower:
            return "double_borrow"

        return f"borrow_error_{code}" if code else "borrow_error_unknown"


class RustBugPatternDetector:
    """Detect Rust-specific bug patterns from borrow checker output."""
    
    PATTERNS = {
        "double_borrow": {
            "pattern_type": "double_borrow",
            "severity": BugSeverity.CRITICAL,
            "description": "Cannot borrow as mutable while immutable borrow exists",
        },
        "double_borrow_mut": {
            "pattern_type": "double_borrow_mut",
            "severity": BugSeverity.CRITICAL,
            "description": "Cannot have multiple mutable borrows",
        },
        "use_after_move": {
            "pattern_type": "use_after_move",
            "severity": BugSeverity.CRITICAL,
            "description": "Use of moved value - value was moved and cannot be used",
        },
        "lifetime_mismatch": {
            "pattern_type": "lifetime_mismatch",
            "severity": BugSeverity.HIGH,
            "description": "Lifetime does not live long enough",
        },
        "move_violation": {
            "pattern_type": "move_violation",
            "severity": BugSeverity.HIGH,
            "description": "Cannot move value - violates ownership rules",
        },
    }
    
    def detect_patterns(
        self,
        errors: List[Dict[str, Any]],
        warnings: List[Dict[str, Any]],
    ) -> List[BugPattern]:
        """Detect true borrow-checker/ownership patterns from diagnostics.

        Only errors categorized as "borrow_check" (see
        BorrowCheckerParser._parse_diagnostic) are eligible — dependency
        resolution errors (missing crate, unresolved import, trait not in
        scope, no main fn) are compilation-environment noise, not memory
        safety findings, and are handled separately by the caller.
        """
        from ..common.interop import ComponentType, LanguageType

        patterns = []

        for error in errors:
            if error.get("category") != "borrow_check":
                continue
            error_type = error.get("type", "")
            if error_type in self.PATTERNS:
                template = self.PATTERNS[error_type]
                pattern = BugPattern(
                    pattern_type=template["pattern_type"],
                    severity=template["severity"],
                    location=f"line {error.get('line', 1)}",
                    description=error.get("message", template["description"]),
                    component=ComponentType.RUST_DEBUG,
                    language=LanguageType.RUST,
                )
                patterns.append(pattern)

        return patterns


# ============================================================================
# Module exports
# ============================================================================

__all__ = [
    "BorrowCheckerParser",
    "RustBugPatternDetector",
]
