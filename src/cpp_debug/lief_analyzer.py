"""
LiefBinaryAnalyzer - binary hardening and dangerous-import checks via lief.

Deliberately NOT a replacement for pyelftools in dwarf_analyzer.py: lief and
pyelftools serve different purposes here. pyelftools' DWARF module walks
compiler-emitted debug info (DIEs) to recover variable types, locations, and
pointer-escape patterns - lief doesn't have comparable DWARF depth. What lief
IS good at, and what DWARFAnalyzer doesn't check at all, is binary-format-
level hardening posture: PIE, NX, stack canary presence, RELRO, and the
imported-symbol table (which flags use of classically dangerous libc
functions like system()/strcpy()/gets() directly from the binary, without
needing source access at all - useful when only a compiled artifact is
available). This is a genuinely different, complementary check, not a
duplicate - same "second opinion" rationale as cppcheck alongside Clang and
valgrind alongside strace elsewhere in this suite.

Verified 2026-07-09: parsed a real compiled binary with lief 0.17.6,
confirmed PIE/NX/RELRO/stack-canary detection toggles correctly between a
default build and one deliberately compiled with
`-fno-stack-protector -Wl,-z,norelro` (canary: True->False, relro stayed
False->False as expected since neither build requested RELRO), and confirmed
dangerous imports (system, strcpy) are correctly listed from the binary's
own import table.

Public API:
    LiefBinaryAnalyzer().analyze(code, dialect="c") -> List[BugPattern]
    lief_available()                                 -> bool
"""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

from ..common.interop import BugPattern, BugSeverity, ComponentType, LanguageType

try:
    import lief
    _LIEF_IMPORTABLE = True
except ImportError:
    lief = None
    _LIEF_IMPORTABLE = False

REQUIRED_TOOLS = {
    "lief": {
        "description": "Binary hardening (PIE/NX/RELRO/stack-canary) and dangerous-import analysis for compiled C/C++ binaries",
        "check": "python3 -c \"import lief; print('ok')\"",
        "install": {
            "pip": "pip install lief",
            "note": "Verified 2026-07-09 via PyPI (pip install lief), no network beyond pypi.org required.",
        },
        "optional": True,  # CppDebugger/CDebugger work fully without it (source-level checks only)
    },
}

# A conservative subset of libc functions with well-known, easy-to-misuse
# unsafe call patterns. Not exhaustive (that's cppcheck/CSA/valgrind's job
# via other detectors) - this flags *use* of the function at all, purely
# from the binary's import table, since even careful use of some of these
# (system, gets) is inherently risky.
_DANGEROUS_IMPORTS = {
    "system": ("command_injection_risk", BugSeverity.HIGH,
               "Binary imports system() - shell command execution. If any argument is influenced by untrusted input, this is a command injection vector."),
    "popen": ("command_injection_risk", BugSeverity.HIGH,
              "Binary imports popen() - shell command execution via a pipe. Same risk profile as system()."),
    "gets": ("unbounded_buffer_read", BugSeverity.CRITICAL,
             "Binary imports gets() - unconditionally unsafe, no bounds checking possible by design. Removed from C11 standard library entirely; its presence usually means the toolchain didn't fully modernize the code."),
    "strcpy": ("unbounded_string_copy", BugSeverity.MEDIUM,
               "Binary imports strcpy() - no bounds checking; safe only if the source is provably no longer than the destination buffer at every call site (not verifiable from the import table alone)."),
    "strcat": ("unbounded_string_concat", BugSeverity.MEDIUM,
               "Binary imports strcat() - no bounds checking, same risk profile as strcpy()."),
    "sprintf": ("unbounded_format_write", BugSeverity.MEDIUM,
                "Binary imports sprintf() - no bounds checking on the output buffer; snprintf() is the safe replacement."),
    "vsprintf": ("unbounded_format_write", BugSeverity.MEDIUM,
                 "Binary imports vsprintf() - no bounds checking on the output buffer; vsnprintf() is the safe replacement."),
}


def lief_available() -> bool:
    """Return True if the lief package is importable."""
    return _LIEF_IMPORTABLE


def _c_compiler() -> str:
    for cc in ("clang", "gcc", "cc"):
        if shutil.which(cc):
            return cc
    return ""


class LiefBinaryAnalyzer:
    """
    Compiles C/C++ source and runs binary hardening + dangerous-import
    checks against the resulting ELF via lief.

    Usage:
        patterns = LiefBinaryAnalyzer().analyze(code, dialect="c")
    """

    def __init__(self, compile_timeout: int = 15):
        self.compile_timeout = compile_timeout

    def analyze(self, code: str, dialect: str = "c", include_hardening: bool = True) -> List[BugPattern]:
        """
        Compile `code` and analyze the resulting binary's hardening
        posture and imports.

        `include_hardening` controls whether binary-wide hardening-posture
        findings (missing NX/PIE/RELRO/stack-canary) are included. These
        are real, accurate findings, but they're a property of the
        compiler/linker flags used, constant across nearly any input
        compiled the same way - not a property of what the code actually
        does. CppDebugger.debug() calls this with include_hardening=False
        so they don't feed the shared risk classifier (which treats *any*
        finding as at least MEDIUM risk - fine for code-content-dependent
        findings like dangerous imports, wrong for a toolchain-constant
        signal that would otherwise flag nearly every program regardless
        of what it does). Call directly with include_hardening=True (the
        default here) to get the full picture, e.g. for a standalone
        binary-hardening audit.

        Degrades gracefully: returns [] if lief isn't installed, there's
        no compiler, or compilation fails (a compile error is a different
        component's job to report - CppDebugger's own diagnostics pass
        already surfaces those; this analyzer only runs on binaries that
        compiled successfully).
        """
        if not lief_available():
            return []

        cc = _c_compiler()
        if not cc:
            return []

        suffix = ".cpp" if dialect == "cpp" else ".c"
        language = LanguageType.CPP if dialect == "cpp" else LanguageType.C

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / f"input{suffix}"
            binary_path = Path(tmpdir) / "input_bin"
            src.write_text(code)

            compile_cmd = [cc, "-g", "-O0"]
            if dialect == "cpp":
                compile_cmd = [cc if cc != "gcc" else "g++", "-g", "-O0", "-std=c++17"]
            else:
                compile_cmd += ["-std=c11"]
            compile_cmd += [str(src), "-o", str(binary_path)]

            try:
                result = subprocess.run(
                    compile_cmd, capture_output=True, text=True, timeout=self.compile_timeout,
                )
                if result.returncode != 0 or not binary_path.exists():
                    return []
            except Exception:
                return []

            try:
                binary = lief.parse(str(binary_path))
                if binary is None:
                    return []
            except Exception:
                return []

            return self._analyze_binary(binary, language, include_hardening)

    def _analyze_binary(self, binary, language: LanguageType, include_hardening: bool = True) -> List[BugPattern]:
        patterns: List[BugPattern] = []

        if not include_hardening:
            return self._dangerous_imports_scan(binary, language)

        patterns.extend(self._dangerous_imports_scan(binary, language))

        # Hardening posture. These are binary-wide, not tied to a source
        # line - location is the binary itself.
        try:
            if not binary.has_nx:
                patterns.append(BugPattern(
                    pattern_type="missing_nx_protection",
                    severity=BugSeverity.MEDIUM,
                    location="binary (link-time flag)",
                    description="Binary lacks NX (non-executable stack/heap) protection. "
                                 "A stack/heap buffer overflow could allow injected shellcode to execute directly.",
                    component=ComponentType.CPP_DEBUG,
                    language=language,
                    suggestion="Ensure the linker isn't passed -z execstack; NX is on by default on modern toolchains unless explicitly disabled.",
                    confidence=0.9,
                ))
        except Exception:
            pass

        try:
            if not binary.is_pie:
                patterns.append(BugPattern(
                    pattern_type="missing_pie",
                    severity=BugSeverity.LOW,
                    location="binary (link-time flag)",
                    description="Binary is not position-independent (no PIE). ASLR provides weaker "
                                 "protection for non-PIE binaries since the main executable's load address is fixed.",
                    component=ComponentType.CPP_DEBUG,
                    language=language,
                    suggestion="Compile/link with -fPIE -pie (default on most modern distros unless explicitly disabled with -no-pie).",
                    confidence=0.9,
                ))
        except Exception:
            pass

        try:
            has_relro = any(
                "GNU_RELRO" in str(s.type) for s in binary.segments
            )
            if not has_relro:
                patterns.append(BugPattern(
                    pattern_type="missing_relro",
                    severity=BugSeverity.LOW,
                    location="binary (link-time flag)",
                    description="Binary lacks RELRO (RELocation Read-Only) hardening. Without it, "
                                 "the GOT (Global Offset Table) remains writable at runtime, a common "
                                 "target for GOT-overwrite exploitation after a memory-corruption bug.",
                    component=ComponentType.CPP_DEBUG,
                    language=language,
                    suggestion="Link with -Wl,-z,relro,-z,now for full RELRO.",
                    confidence=0.85,
                ))
        except Exception:
            pass

        try:
            has_canary = any(s.name == "__stack_chk_fail" for s in binary.symbols)
            if not has_canary:
                patterns.append(BugPattern(
                    pattern_type="missing_stack_canary",
                    severity=BugSeverity.MEDIUM,
                    location="binary (compile-time flag)",
                    description="Binary shows no evidence of stack-protector instrumentation "
                                 "(__stack_chk_fail not found in the symbol table). A stack buffer "
                                 "overflow could overwrite the return address undetected.",
                    component=ComponentType.CPP_DEBUG,
                    language=language,
                    suggestion="Compile with -fstack-protector-strong (on by default on most modern distros unless explicitly disabled).",
                    confidence=0.75,  # symbol may be stripped even if the instrumentation is present
                ))
        except Exception:
            pass

        return patterns

    def _dangerous_imports_scan(self, binary, language: LanguageType) -> List[BugPattern]:
        """Scan the binary's import table for classically dangerous libc functions."""
        patterns: List[BugPattern] = []
        try:
            seen = set()
            for func in binary.imported_functions:
                # Import names sometimes carry a "@GLIBC_x.y.z" version
                # suffix - strip it for matching, but keep the raw name for
                # dedup so "system" and "system@GLIBC_2.2.5" aren't reported
                # twice.
                base_name = func.name.split("@")[0]
                if base_name in _DANGEROUS_IMPORTS and base_name not in seen:
                    seen.add(base_name)
                    itype, sev, desc = _DANGEROUS_IMPORTS[base_name]
                    patterns.append(BugPattern(
                        pattern_type=f"dangerous_import_{base_name}",
                        severity=sev,
                        location=f"binary import table: {base_name}",
                        description=desc,
                        component=ComponentType.CPP_DEBUG,
                        language=language,
                        suggestion=f"Review every call site of {base_name}() for untrusted input reaching it.",
                        confidence=0.8,
                    ))
        except Exception:
            pass
        return patterns


__all__ = ["LiefBinaryAnalyzer", "lief_available", "REQUIRED_TOOLS"]
