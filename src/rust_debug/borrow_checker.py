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
    
    def _parse_diagnostic(self, diagnostic: Dict[str, Any]) -> Dict[str, Any]:
        """Convert rustc diagnostic to standard format."""
        spans = diagnostic.get('spans', [])
        line = spans[0]['line_start'] if spans else 1
        
        message = diagnostic.get('message', '')
        code = diagnostic.get('code', {}).get('code', '')
        
        return {
            "type": self._classify_error(message, code),
            "message": message,
            "code": code,
            "line": line,
            "column": spans[0].get('column_start', 1) if spans else 1,
        }
    
    def _classify_error(self, message: str, code: str) -> str:
        """Classify borrow checker error type."""
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
        
        return f"borrow_error_{code}"


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
        """Detect patterns from borrow checker diagnostics."""
        from ..common.interop import ComponentType, LanguageType
        
        patterns = []
        
        for error in errors:
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
