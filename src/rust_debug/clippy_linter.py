"""
Phase 3: Rust-Debug Clippy Integration

Runs Clippy (Rust linter) and extracts warnings/suggestions.
Converts lint messages into BugPattern objects.

Requires: clippy (installed via: rustup component add clippy)

Usage:
    clippy = ClippyLinter()
    patterns = clippy.run_clippy(code)
"""

import json
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..common.interop import BugPattern, BugSeverity


class ClippyLinter:
    """Run Clippy linter and extract lint warnings."""
    
    def __init__(self):
        self.clippy_available = self._check_clippy()
    
    def _check_clippy(self) -> bool:
        """Check if clippy is available."""
        try:
            subprocess.run(
                ["cargo", "clippy", "--version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def run_clippy(self, code: str) -> List[BugPattern]:
        """
        Run Clippy on Rust code and return detected patterns.
        
        Args:
            code: Rust source code
        
        Returns:
            List of BugPattern objects
        """
        if not self.clippy_available:
            return []
        
        # Write code to temp file with Cargo.toml
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create Cargo.toml
            cargo_toml = tmpdir_path / "Cargo.toml"
            cargo_toml.write_text("""
[package]
name = "debug_check"
version = "0.1.0"
edition = "2021"
""")
            
            # Create src/main.rs
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "main.rs").write_text(code)
            
            try:
                # Run cargo clippy with JSON output
                result = subprocess.run(
                    ["cargo", "clippy", "--message-format=json"],
                    cwd=str(tmpdir_path),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                
                patterns = []
                for line in result.stdout.split('\n') + result.stderr.split('\n'):
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                        if msg.get('level') in ['warning', 'error']:
                            pattern = self._parse_clippy_message(msg)
                            if pattern:
                                patterns.append(pattern)
                    except json.JSONDecodeError:
                        pass
                
                return patterns
            
            except subprocess.TimeoutExpired:
                return []
            except Exception as e:
                print(f"[Clippy] Error: {e}", file=sys.stderr)
                return []
    
    def _parse_clippy_message(self, message: Dict[str, Any]) -> Optional[BugPattern]:
        """Convert Clippy JSON message to BugPattern."""
        if not message.get('message'):
            return None
        
        from ..common.interop import ComponentType, LanguageType
        
        msg_text = message.get('message', {})
        if isinstance(msg_text, dict):
            text = msg_text.get('text', '')
            code = msg_text.get('code', {}).get('code', '')
        else:
            text = str(msg_text)
            code = ''
        
        # Extract line number
        spans = message.get('spans', [])
        line = spans[0]['line_start'] if spans else 1
        
        # Classify severity
        level = message.get('level', 'warning')
        severity = (
            BugSeverity.CRITICAL if level == 'error'
            else BugSeverity.HIGH if 'panic' in text.lower()
            else BugSeverity.MEDIUM if 'unsafe' in text.lower()
            else BugSeverity.LOW
        )
        
        # Classify pattern type
        pattern_type = self._classify_clippy_lint(code, text)
        
        return BugPattern(
            pattern_type=pattern_type,
            severity=severity,
            location=f"line {line}",
            description=text,
            component=ComponentType.STATIC,
            language=LanguageType.RUST,
        )
    
    def _classify_clippy_lint(self, code: str, text: str) -> str:
        """Classify Clippy lint type."""
        code_lower = code.lower()
        text_lower = text.lower()
        
        # Common clippy patterns
        if 'unused' in code_lower or 'unused' in text_lower:
            return "clippy_unused"
        if 'needless' in code_lower or 'unnecessary' in text_lower:
            return "clippy_unnecessary"
        if 'panic' in code_lower:
            return "clippy_panic"
        if 'unsafe' in code_lower:
            return "clippy_unsafe"
        if 'clone' in code_lower or 'clone' in text_lower:
            return "clippy_clone"
        if 'format' in code_lower:
            return "clippy_format"
        if 'iterator' in code_lower or 'iter' in text_lower:
            return "clippy_iterator"
        if 'regex' in code_lower:
            return "clippy_regex"
        if 'perf' in code_lower:
            return "clippy_perf"
        
        return f"clippy_{code}" if code else "clippy_warning"


class CliPPYMerger:
    """Merge Clippy warnings with borrow checker errors."""
    
    @staticmethod
    def merge_results(
        borrow_patterns: List[BugPattern],
        clippy_patterns: List[BugPattern],
    ) -> List[BugPattern]:
        """Merge patterns from both sources, avoiding duplicates."""
        # Start with borrow checker (higher priority)
        merged = list(borrow_patterns)
        
        # Add clippy patterns (check for duplicates by line/type)
        seen = {(p.line, p.pattern_type) for p in merged}
        for pattern in clippy_patterns:
            key = (pattern.line, pattern.pattern_type)
            if key not in seen:
                merged.append(pattern)
                seen.add(key)
        
        # Sort by severity then line
        severity_order = {
            BugSeverity.CRITICAL: 0,
            BugSeverity.HIGH: 1,
            BugSeverity.MEDIUM: 2,
            BugSeverity.LOW: 3,
            BugSeverity.INFO: 4,
        }
        
        merged.sort(
            key=lambda p: (severity_order.get(p.severity, 5), p.line)
        )
        
        return merged


# ============================================================================
# Module exports
# ============================================================================

__all__ = [
    "ClippyLinter",
    "CliPPYMerger",
]
