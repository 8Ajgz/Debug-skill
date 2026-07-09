"""
SemgrepAnalyzer - pattern-based static analysis via semgrep.

Complements bandit (Phase 0's other security tool - see
master_debugger/phases.py) rather than duplicating it: bandit's checks are
hand-coded Python AST visitors baked into the bandit package itself, while
semgrep's checks are declarative YAML pattern rules, so the two tools
frequently catch overlapping bug classes with different rule authors and
different edge-case coverage - the same "second opinion" rationale as
CppcheckAnalyzer alongside Clang's own diagnostics (see
cpp_debug/cppcheck_analyzer.py).

Uses a locally-bundled rule subset (src/common/semgrep_rules/) rather than
`semgrep --config auto`, because the default registry-based configs fetch
from semgrep.dev at request time, which returned `HTTP 403` when tested
from this sandbox (2026-07-09) - the network allowlist covers github.com/
codeload.github.com but not semgrep.dev. See semgrep_rules/README.md for
provenance and how to refresh/expand the bundled rules.

Public API:
    SemgrepAnalyzer().analyze(code, language="python") -> List[BugPattern]
    semgrep_available()                                 -> bool
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

from .interop import BugPattern, BugSeverity, ComponentType, LanguageType

REQUIRED_TOOLS = {
    "semgrep": {
        "description": "Pattern-based static analysis (security rules), second opinion alongside bandit/cppcheck",
        "check": "semgrep --version",
        "install": {
            "pip": "pip install semgrep --break-system-packages",
            "note": (
                "Verified 2026-07-09 via PyPI (pip install semgrep). "
                "Rules are bundled locally under semgrep_rules/ since "
                "semgrep.dev's registry (--config auto) is not reachable "
                "from sandboxed environments - do not pass --config auto."
            ),
        },
        "optional": True,  # Phase0StaticAnalysis degrades to mypy+pylint+bandit without it
    },
}

# Bundled rule directories, keyed by language. Only python_security exists
# as of v2.6.0 - see semgrep_rules/README.md "Scope note" for how to add more.
_RULES_DIR = Path(__file__).parent / "semgrep_rules"
_LANGUAGE_RULESETS = {
    "python": _RULES_DIR / "python_security",
}

# semgrep severities: ERROR, WARNING, INFO
_SEVERITY_MAP = {
    "ERROR": BugSeverity.HIGH,
    "WARNING": BugSeverity.MEDIUM,
    "INFO": BugSeverity.LOW,
}


def semgrep_available() -> bool:
    """Return True if semgrep is on PATH."""
    return shutil.which("semgrep") is not None


class SemgrepAnalyzer:
    """
    Runs semgrep against source code using a bundled, offline rule subset.

    Usage:
        patterns = SemgrepAnalyzer().analyze(code, language="python")
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def analyze(self, code: str, language: str = "python") -> List[BugPattern]:
        """
        Run semgrep against `code` using the bundled ruleset for `language`.

        Degrades gracefully: returns [] if semgrep isn't installed, no
        bundled ruleset exists for `language`, or the run fails outright.
        """
        if not semgrep_available():
            return []

        ruleset = _LANGUAGE_RULESETS.get(language)
        if ruleset is None or not ruleset.is_dir():
            return []

        suffix = {"python": ".py", "javascript": ".js"}.get(language, ".txt")
        lang_type = {"python": LanguageType.PYTHON, "javascript": LanguageType.JAVASCRIPT}.get(
            language, LanguageType.PYTHON
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / f"input{suffix}"
            src.write_text(code)

            try:
                result = subprocess.run(
                    [
                        "semgrep",
                        "--config", str(ruleset),
                        "--json",
                        "--quiet",
                        "--no-git-ignore",
                        str(src),
                    ],
                    capture_output=True, text=True, timeout=self.timeout,
                )
            except subprocess.TimeoutExpired:
                return []
            except Exception:
                return []

            return self._parse_json(result.stdout, lang_type, src.name)

    def _parse_json(self, stdout: str, language: LanguageType, filename: str) -> List[BugPattern]:
        patterns: List[BugPattern] = []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return patterns

        for r in data.get("results", []):
            check_id = r.get("check_id", "unknown")
            # check_id is a dotted path like
            # "semgrep_rules.python_security.audit.subprocess-shell-true" -
            # take just the last, human-meaningful segment.
            short_id = check_id.split(".")[-1]
            extra = r.get("extra", {})
            severity = _SEVERITY_MAP.get(extra.get("severity", "WARNING"), BugSeverity.MEDIUM)
            line = r.get("start", {}).get("line", "?")
            message = extra.get("message", short_id).strip()

            patterns.append(BugPattern(
                pattern_type=f"semgrep_{short_id}",
                severity=severity,
                location=f"{filename}:{line}",
                description=message,
                component=ComponentType.PYTHON_DEBUG if language == LanguageType.PYTHON else ComponentType.JAVASCRIPT_DEBUG,
                language=language,
                suggestion="See semgrep rule metadata for remediation guidance "
                           f"(rule: {short_id}).",
                confidence=0.85,
            ))

        return patterns


__all__ = ["SemgrepAnalyzer", "semgrep_available", "REQUIRED_TOOLS"]
