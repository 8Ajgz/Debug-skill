"""
Rust-Debug Phase 0: Static Analysis

Real pre-compile pattern detection that does not require rustc/cargo to be
installed or the crate's dependency graph to resolve:

- incomplete-code markers: todo!()/unimplemented!()/unreachable!() macro
  calls, which are real, substantive signal that code isn't finished --
  independent of whether it happens to compile.
- delimiter balance: catches truncated/malformed source before any
  compilation is attempted, so this still gives a real result even when
  rustc isn't installed at all (Phase 1 then never runs, see
  rust_debug/setup.py).
- lint-suppression attributes (#[allow(...)]): not bugs by themselves, but
  worth surfacing since they can mask issues Phase 1 (clippy) would
  otherwise report.

This replaces the previous `phase_0_ok = True  # Placeholder` /
`phase_0_static()` stub (see STUBS.md). It is intentionally scoped to
regex/lexical scanning, not a real AST -- there is no standalone Rust
parser available in this environment, and Phase 1's own rustc invocation
is the suite's actual syntax authority. That is an honest, documented
limitation (mirrors Python's Phase 0, which likewise degrades gracefully
when mypy/pylint/bandit aren't installed), not a claim of full AST-level
analysis.
"""

import re
from dataclasses import dataclass, field
from typing import List

from ..common.interop import BugPattern, BugSeverity, ComponentType, LanguageType


@dataclass
class StaticAnalysisResult:
    """Result of Phase 0 static analysis."""
    passed: bool
    incomplete_code_markers: List[str] = field(default_factory=list)
    delimiter_balanced: bool = True
    delimiter_errors: List[str] = field(default_factory=list)
    lint_suppressions: List[str] = field(default_factory=list)
    patterns: List[BugPattern] = field(default_factory=list)


class RustStaticAnalyzer:
    """Real pre-compile static analysis for Rust source, no toolchain required."""

    _INCOMPLETE_MACROS = re.compile(r'\b(todo|unimplemented|unreachable)!\s*\(')
    _LINT_SUPPRESSION = re.compile(r'#!?\[\s*allow\(([^)]*)\)\s*\]')

    _OPENERS = {'{': '}', '(': ')', '[': ']'}
    _CLOSERS = {v: k for k, v in _OPENERS.items()}

    def analyze(self, code: str) -> StaticAnalysisResult:
        result = StaticAnalysisResult(passed=True)
        stripped = self._strip_strings_and_comments(code)

        # 1. Incomplete-code markers.
        for m in self._INCOMPLETE_MACROS.finditer(stripped):
            line = stripped[:m.start()].count('\n') + 1
            marker = m.group(1)
            result.incomplete_code_markers.append(f"{marker}!() at line {line}")
            result.patterns.append(BugPattern(
                pattern_type="INCOMPLETE_CODE",
                severity=BugSeverity.HIGH,
                location=f"line {line}",
                description=f"{marker}!() macro indicates incomplete implementation",
                component=ComponentType.RUST_DEBUG,
                language=LanguageType.RUST,
                suggestion="Implement the missing logic before shipping",
                confidence=1.0,
            ))

        # 2. Delimiter balance.
        stack = []
        for i, ch in enumerate(stripped):
            if ch in self._OPENERS:
                stack.append((ch, i))
            elif ch in self._CLOSERS:
                if not stack or stack[-1][0] != self._CLOSERS[ch]:
                    line = stripped[:i].count('\n') + 1
                    result.delimiter_balanced = False
                    result.delimiter_errors.append(f"unmatched '{ch}' at line {line}")
                else:
                    stack.pop()
        for ch, i in stack:
            line = stripped[:i].count('\n') + 1
            result.delimiter_balanced = False
            result.delimiter_errors.append(f"unclosed '{ch}' at line {line}")

        if not result.delimiter_balanced:
            result.patterns.append(BugPattern(
                pattern_type="UNBALANCED_DELIMITERS",
                severity=BugSeverity.CRITICAL,
                location="; ".join(result.delimiter_errors[:5]),
                description="Source has unbalanced braces/parens/brackets and will not compile",
                component=ComponentType.RUST_DEBUG,
                language=LanguageType.RUST,
                suggestion="Fix delimiter mismatch before compiling",
                confidence=0.95,
            ))

        # 3. Lint suppressions (informational, not a pattern/finding).
        for m in self._LINT_SUPPRESSION.finditer(stripped):
            result.lint_suppressions.append(m.group(1).strip())

        result.passed = result.delimiter_balanced and not result.incomplete_code_markers
        return result

    @staticmethod
    def _strip_strings_and_comments(code: str) -> str:
        """Best-effort removal of string literals and comments so delimiter
        balance / macro checks don't false-positive on braces or macro-like
        text inside a string or a commented-out line. Not a full lexer --
        does not special-case raw strings (r"...") or char-literal quoting,
        since those essentially never contain the brace/paren/bracket
        characters this check cares about, and getting that distinction
        wrong would risk introducing new false positives rather than
        removing them. Line length is preserved (replaced with spaces) so
        reported line numbers stay accurate.
        """
        out = []
        i = 0
        n = len(code)
        in_line_comment = False
        in_block_comment = False
        in_string = False
        while i < n:
            c = code[i]
            nxt = code[i + 1] if i + 1 < n else ''
            if in_line_comment:
                if c == '\n':
                    in_line_comment = False
                    out.append('\n')
                else:
                    out.append(' ')
                i += 1
                continue
            if in_block_comment:
                if c == '*' and nxt == '/':
                    in_block_comment = False
                    out.append('  ')
                    i += 2
                else:
                    out.append('\n' if c == '\n' else ' ')
                    i += 1
                continue
            if in_string:
                if c == '\\' and i + 1 < n:
                    out.append('  ')
                    i += 2
                    continue
                if c == '"':
                    in_string = False
                    out.append(' ')
                else:
                    out.append('\n' if c == '\n' else ' ')
                i += 1
                continue
            if c == '/' and nxt == '/':
                in_line_comment = True
                out.append('  ')
                i += 2
                continue
            if c == '/' and nxt == '*':
                in_block_comment = True
                out.append('  ')
                i += 2
                continue
            if c == '"':
                in_string = True
                out.append(' ')
                i += 1
                continue
            out.append(c)
            i += 1
        return ''.join(out)


__all__ = ["RustStaticAnalyzer", "StaticAnalysisResult"]
