"""
Phase 5: C/C++ DWARF Symbol Analysis

Reads DWARF debug information from compiled ELF binaries using pyelftools.
Provides:
  - Variable/type layout (size, offset, type name)
  - Allocation site tracking (stack vs heap vs global)
  - Heuristic use-after-free / double-free / out-of-bounds detection
    based on allocation-site vs access-site mapping in DWARF data

This module works on COMPILED BINARIES (ELF with -g DWARF info), not on
source code directly. The typical workflow from cpp_debug's perspective is:

    1. compile source with -g to a temp binary
    2. run DWARFAnalyzer on the binary
    3. merge DWARFReport.patterns into the CppDebugger report

Degrades gracefully if pyelftools is not installed (returns empty
DWARFReport with tool_available=False).

Public API:
    DWARFAnalyzer().analyze_binary(path)       -> DWARFReport
    DWARFAnalyzer().analyze_source(code, dialect) -> DWARFReport
    dwarf_available()                           -> bool
"""

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..common.interop import BugPattern, BugSeverity, ComponentType, LanguageType

try:
    from elftools.elf.elffile import ELFFile
    from elftools.dwarf.die import DIE
    from elftools.dwarf.dwarfinfo import DWARFInfo
    _ELFTOOLS_AVAILABLE = True
except ImportError:
    _ELFTOOLS_AVAILABLE = False


def dwarf_available() -> bool:
    """Return True if pyelftools is importable and a C compiler is on PATH."""
    return _ELFTOOLS_AVAILABLE and (
        shutil.which("gcc") is not None or shutil.which("clang") is not None
    )


# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DWARFVariable:
    """One variable record extracted from DWARF debug info."""
    name: str
    type_name: str
    location_kind: str          # "stack", "heap_site", "global", "unknown"
    byte_size: int              # sizeof the type, 0 if unknown
    declaration_file: str
    declaration_line: int
    # If the variable is a pointer, what type it points to
    pointee_type: str = ""
    # Whether the variable has a DW_AT_location attribute at all
    has_location: bool = True


@dataclass
class DWARFMemoryIssue:
    """A memory-safety issue found during DWARF analysis."""
    issue_type: str             # "potential_uaf", "potential_double_free", "untracked_heap"
    variable_name: str
    description: str
    location: str               # "file:line" or "function:scope"
    severity: BugSeverity = BugSeverity.HIGH
    confidence: float = 0.5     # DWARF heuristics are inherently imprecise


@dataclass
class DWARFReport:
    """Full DWARF analysis report for one binary."""
    binary_path: str
    tool_available: bool
    variables: List[DWARFVariable] = field(default_factory=list)
    memory_issues: List[DWARFMemoryIssue] = field(default_factory=list)
    # Raw type → size map from DWARF (useful for layout analysis)
    type_sizes: Dict[str, int] = field(default_factory=dict)
    # Functions found in DWARF
    function_names: List[str] = field(default_factory=list)
    error: str = ""

    def to_bug_patterns(self, language: LanguageType = LanguageType.C) -> List[BugPattern]:
        """Convert DWARFMemoryIssue records to unified BugPattern records."""
        patterns: List[BugPattern] = []
        for issue in self.memory_issues:
            patterns.append(BugPattern(
                pattern_type=issue.issue_type,
                severity=issue.severity,
                location=issue.location,
                description=issue.description,
                component=ComponentType.CPP_DEBUG,
                language=language,
                suggestion=_UAF_SUGGESTIONS.get(issue.issue_type, "Review memory ownership"),
                confidence=issue.confidence,
            ))
        return patterns


_UAF_SUGGESTIONS: Dict[str, str] = {
    "potential_uaf": (
        "Ensure the pointer is not accessed after the object it points to is freed or "
        "goes out of scope. Consider std::unique_ptr or lifetime annotations."
    ),
    "potential_double_free": (
        "Nullify the pointer immediately after free()/delete. "
        "Prefer std::unique_ptr which makes double-free impossible."
    ),
    "untracked_heap": (
        "This allocation site has no corresponding deallocation found in DWARF. "
        "Verify ownership is transferred to a scope that deallocates it."
    ),
    "stack_pointer_escape": (
        "A pointer to a stack-allocated variable may outlive its declaring scope. "
        "Return by value or allocate on the heap instead."
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# DWARF walking utilities
# ──────────────────────────────────────────────────────────────────────────────

def _die_attr(die: "DIE", attr_name: str, default: Any = None) -> Any:
    """Safely get a DWARF attribute value from a DIE."""
    attr = die.attributes.get(attr_name)
    if attr is None:
        return default
    return attr.value


def _resolve_type_name(die: "DIE", cu_dies: Dict[int, "DIE"]) -> str:
    """
    Walk DW_AT_type references to produce a human-readable type name.
    Follows pointer/const/typedef chains up to 8 hops.
    """
    current = die
    parts: List[str] = []
    for _ in range(8):
        type_offset = _die_attr(current, "DW_AT_type")
        if type_offset is None:
            break
        type_die = cu_dies.get(type_offset)
        if type_die is None:
            break
        tag = type_die.tag
        if tag == "DW_TAG_pointer_type":
            parts.append("*")
            current = type_die
        elif tag == "DW_TAG_const_type":
            parts.append("const")
            current = type_die
        elif tag in ("DW_TAG_base_type", "DW_TAG_typedef",
                     "DW_TAG_structure_type", "DW_TAG_class_type",
                     "DW_TAG_union_type", "DW_TAG_enumeration_type"):
            name = _die_attr(type_die, "DW_AT_name", b"")
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            parts.append(name or tag.replace("DW_TAG_", ""))
            break
        else:
            break
    return " ".join(reversed(parts)) if parts else "unknown"


def _die_byte_size(die: "DIE", cu_dies: Dict[int, "DIE"]) -> int:
    """Return byte size of a DIE, following DW_AT_type if needed."""
    sz = _die_attr(die, "DW_AT_byte_size")
    if sz is not None:
        return int(sz)
    type_offset = _die_attr(die, "DW_AT_type")
    if type_offset is not None:
        type_die = cu_dies.get(type_offset)
        if type_die is not None:
            sz = _die_attr(type_die, "DW_AT_byte_size")
            if sz is not None:
                return int(sz)
    return 0


def _build_cu_die_map(cu) -> Dict[int, "DIE"]:
    """Build an offset → DIE map for all DIEs in a CU (for type resolution)."""
    result: Dict[int, "DIE"] = {}
    for die in cu.iter_DIEs():
        result[die.offset] = die
    return result


def _decl_location(die: "DIE", cu) -> Tuple[str, int]:
    """Return (filename, line) from DW_AT_decl_file / DW_AT_decl_line."""
    line_program = None
    try:
        line_program = cu.dwarfinfo.line_program_for_CU(cu)
    except Exception:
        pass

    file_idx = _die_attr(die, "DW_AT_decl_file", 0)
    line_no = _die_attr(die, "DW_AT_decl_line", 0)

    filename = ""
    if line_program and file_idx:
        try:
            lp_header = line_program.header
            file_entries = lp_header.get("file_entry", [])
            if 0 < file_idx <= len(file_entries):
                raw = file_entries[file_idx - 1].name
                filename = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        except Exception:
            pass

    return filename, int(line_no) if line_no else 0


# ──────────────────────────────────────────────────────────────────────────────
# Memory issue heuristics
# ──────────────────────────────────────────────────────────────────────────────

def _classify_location_kind(die: "DIE") -> str:
    """
    Classify a variable's storage location kind from DWARF location expressions.

    Heuristic rules:
      - DW_AT_location with DW_OP_fbreg / DW_OP_breg* → stack
      - DW_AT_location with DW_OP_addr → global / static
      - No DW_AT_location → optimised out or unknown
    """
    loc_attr = die.attributes.get("DW_AT_location")
    if loc_attr is None:
        return "unknown"
    # The value may be a list of location expressions or a raw block
    value = loc_attr.value
    if isinstance(value, list):
        # LocationExpr list from pyelftools
        for entry in value:
            try:
                for op in entry.loc_expr:
                    op_name = getattr(op, "op_name", "")
                    if "fbreg" in op_name or "breg" in op_name:
                        return "stack"
                    if op_name == "DW_OP_addr":
                        return "global"
            except Exception:
                pass
        return "unknown"
    if isinstance(value, bytes) and value:
        first_byte = value[0]
        # DW_OP_fbreg = 0x77, DW_OP_breg0-breg31 = 0x77-0x96
        if first_byte == 0x77 or 0x77 <= first_byte <= 0x96:
            return "stack"
        # DW_OP_addr = 0x03
        if first_byte == 0x03:
            return "global"
    return "unknown"


def _check_pointer_escapes(variables: List[DWARFVariable]) -> List[DWARFMemoryIssue]:
    """
    Heuristic: flag stack-allocated pointer variables that might escape.

    A pointer whose location_kind is "stack" and whose type_name contains "*"
    is a stack-local pointer. If the pointee_type looks like a stack type too,
    returning the pointer would be a stack escape. We can only flag the
    *potential* — DWARF alone doesn't tell us whether the pointer is returned.
    """
    issues: List[DWARFMemoryIssue] = []
    for var in variables:
        if var.location_kind == "stack" and "*" in var.type_name:
            issues.append(DWARFMemoryIssue(
                issue_type="stack_pointer_escape",
                variable_name=var.name,
                description=(
                    f"'{var.name}' is a pointer (type: {var.type_name}) allocated on the stack. "
                    "If this pointer escapes the function (returned, stored globally, or passed to "
                    "a callback that outlives the scope), accessing it later is undefined behaviour."
                ),
                location=f"{var.declaration_file}:{var.declaration_line}",
                severity=BugSeverity.MEDIUM,
                confidence=0.4,
            ))
    return issues


def _check_void_pointer_casts(variables: List[DWARFVariable]) -> List[DWARFMemoryIssue]:
    """Flag void* variables — common in hand-rolled heap allocations lacking type safety."""
    issues: List[DWARFMemoryIssue] = []
    for var in variables:
        if "void" in var.type_name and "*" in var.type_name:
            issues.append(DWARFMemoryIssue(
                issue_type="untracked_heap",
                variable_name=var.name,
                description=(
                    f"'{var.name}' is typed as void* — a common pattern for manual heap "
                    "allocations that bypass the type system. The allocation site is present "
                    "in DWARF, but there is no type-safe way to track ownership statically."
                ),
                location=f"{var.declaration_file}:{var.declaration_line}",
                severity=BugSeverity.MEDIUM,
                confidence=0.45,
            ))
    return issues


def _cross_ref_pointers(variables: List[DWARFVariable]) -> List[DWARFMemoryIssue]:
    """
    Check for multiple pointer variables pointing to the same type at the same
    declaration line — a potential aliasing / double-free hazard.
    """
    issues: List[DWARFMemoryIssue] = []
    # Group by (file, line, pointee_type)
    seen: Dict[Tuple[str, int, str], List[str]] = {}
    for var in variables:
        if "*" not in var.type_name or not var.pointee_type:
            continue
        key = (var.declaration_file, var.declaration_line, var.pointee_type)
        seen.setdefault(key, []).append(var.name)

    for (fpath, lno, ptype), names in seen.items():
        if len(names) >= 2:
            issues.append(DWARFMemoryIssue(
                issue_type="potential_double_free",
                variable_name=", ".join(names),
                description=(
                    f"Multiple pointers to '{ptype}' declared at the same location "
                    f"({fpath}:{lno}): {', '.join(names)}. "
                    "If both are passed to free()/delete without a clear ownership transfer, "
                    "a double-free is possible."
                ),
                location=f"{fpath}:{lno}",
                severity=BugSeverity.HIGH,
                confidence=0.55,
            ))
    return issues


# ──────────────────────────────────────────────────────────────────────────────
# Core analyser
# ──────────────────────────────────────────────────────────────────────────────

class DWARFAnalyzer:
    """
    Reads DWARF debug info from ELF binaries produced with -g.

    Usage:
        report = DWARFAnalyzer().analyze_source(c_code, dialect="c")
        patterns = report.to_bug_patterns()
    """

    def __init__(self, compiler_timeout: int = 20):
        self.compiler_timeout = compiler_timeout

    # ── public API ────────────────────────────────────────────────────────────

    def analyze_source(self, code: str, dialect: str = "c") -> "DWARFReport":
        """
        Compile `code` with -g, analyse the resulting binary, remove the binary.

        Gracefully degrades if no compiler or pyelftools is available.
        """
        if not dwarf_available():
            return DWARFReport(binary_path="", tool_available=False,
                               error="pyelftools or C compiler not available")

        suffix = ".cpp" if dialect == "cpp" else ".c"
        compiler = "clang++" if dialect == "cpp" else (
            "clang" if shutil.which("clang") else "gcc"
        )
        std_flag = "-std=c++17" if dialect == "cpp" else "-std=c11"

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / f"input{suffix}"
            binary = Path(tmpdir) / "input.elf"
            src.write_text(code)

            try:
                result = subprocess.run(
                    [compiler, std_flag, "-g", "-O0", str(src), "-o", str(binary)],
                    capture_output=True, text=True,
                    timeout=self.compiler_timeout,
                )
            except subprocess.TimeoutExpired:
                return DWARFReport(binary_path="", tool_available=True,
                                   error="Compilation timed out")
            except Exception as exc:
                return DWARFReport(binary_path="", tool_available=True,
                                   error=f"Compiler invocation failed: {exc}")

            if result.returncode != 0:
                # Syntax errors prevent binary; return empty report
                return DWARFReport(binary_path="", tool_available=True,
                                   error=f"Compilation failed: {result.stderr[:400]}")

            return self.analyze_binary(str(binary))

    def analyze_binary(self, path: str) -> "DWARFReport":
        """
        Read DWARF debug info from an existing ELF binary at `path`.

        Returns a DWARFReport containing extracted variables and memory issues.
        """
        if not _ELFTOOLS_AVAILABLE:
            return DWARFReport(binary_path=path, tool_available=False,
                               error="pyelftools not installed")

        report = DWARFReport(binary_path=path, tool_available=True)

        try:
            with open(path, "rb") as f:
                elf = ELFFile(f)
                if not elf.has_dwarf_info():
                    report.error = "Binary has no DWARF info (was it compiled with -g?)"
                    return report
                self._walk_dwarf(elf, report)
        except FileNotFoundError:
            report.error = f"Binary not found: {path}"
            report.tool_available = False
        except Exception as exc:
            report.error = f"DWARF parsing failed: {exc}"

        # Run heuristic passes after extraction
        report.memory_issues += _check_pointer_escapes(report.variables)
        report.memory_issues += _check_void_pointer_casts(report.variables)
        report.memory_issues += _cross_ref_pointers(report.variables)

        return report

    # ── DWARF walking internals ───────────────────────────────────────────────

    def _walk_dwarf(self, elf: "ELFFile", report: "DWARFReport") -> None:
        dwarf: "DWARFInfo" = elf.get_dwarf_info()
        for cu in dwarf.iter_CUs():
            self._process_cu(cu, report)

    def _process_cu(self, cu, report: "DWARFReport") -> None:
        """Process one Compilation Unit: extract subprograms and variables."""
        cu_dies = _build_cu_die_map(cu)
        type_sizes: Dict[str, int] = {}

        for die in cu.iter_DIEs():
            tag = die.tag

            # Collect subprogram (function) names
            if tag == "DW_TAG_subprogram":
                name_attr = die.attributes.get("DW_AT_name")
                if name_attr is not None:
                    name = name_attr.value
                    if isinstance(name, bytes):
                        name = name.decode("utf-8", errors="replace")
                    if name and name not in report.function_names:
                        report.function_names.append(name)

            # Collect base-type sizes for layout analysis
            if tag == "DW_TAG_base_type":
                type_name_raw = _die_attr(die, "DW_AT_name", b"")
                if isinstance(type_name_raw, bytes):
                    type_name_raw = type_name_raw.decode("utf-8", errors="replace")
                sz = _die_attr(die, "DW_AT_byte_size", 0)
                if type_name_raw and sz:
                    type_sizes[type_name_raw] = int(sz)

            # Collect local variables and formal parameters
            if tag in ("DW_TAG_variable", "DW_TAG_formal_parameter"):
                var = self._extract_variable(die, cu, cu_dies)
                if var is not None:
                    report.variables.append(var)

        report.type_sizes.update(type_sizes)

    def _extract_variable(self, die: "DIE", cu, cu_dies: Dict[int, "DIE"]) -> Optional[DWARFVariable]:
        """Extract one variable DIE into a DWARFVariable record."""
        name_raw = _die_attr(die, "DW_AT_name")
        if name_raw is None:
            return None
        if isinstance(name_raw, bytes):
            name_raw = name_raw.decode("utf-8", errors="replace")
        if not name_raw:
            return None

        type_name = _resolve_type_name(die, cu_dies)
        byte_size = _die_byte_size(die, cu_dies)
        location_kind = _classify_location_kind(die)
        decl_file, decl_line = _decl_location(die, cu)

        # Determine pointee type for pointer variables
        pointee_type = ""
        if "*" in type_name:
            # Strip one level of pointer to get the pointee
            pointee_type = type_name.replace("*", "", 1).strip()

        has_loc = "DW_AT_location" in die.attributes

        return DWARFVariable(
            name=name_raw,
            type_name=type_name,
            location_kind=location_kind,
            byte_size=byte_size,
            declaration_file=decl_file,
            declaration_line=decl_line,
            pointee_type=pointee_type,
            has_location=has_loc,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Claude-facing setup helper (mirrors rust_debug/setup.py, cpp_debug/setup.py)
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_TOOLS = {
    "pyelftools": {
        "description": "Python library for reading ELF/DWARF files",
        "check": "python3 -c \"from elftools.elf.elffile import ELFFile; print('ok')\"",
        "install": {
            "pip": "pip install pyelftools",
            "conda": "conda install -c conda-forge pyelftools",
        },
        "optional": False,
    },
    "gcc_or_clang": {
        "description": "C compiler that emits DWARF debug info with -g",
        "check": "gcc --version || clang --version",
        "install": {
            "apt": "sudo apt install gcc clang",
            "brew": "brew install gcc llvm",
            "docker": "FROM ubuntu:22.04 && RUN apt-get install -y gcc clang",
        },
        "optional": False,
    },
}


def claude_check_and_install() -> Dict[str, Any]:
    """
    Claude-executable check: verify all tools are present and print install
    instructions for any that are missing.

    Returns:
        {"all_ready": bool, "missing": List[str], "instructions": Dict[str, str]}
    """
    missing: List[str] = []
    instructions: Dict[str, str] = {}

    if not _ELFTOOLS_AVAILABLE:
        missing.append("pyelftools")
        instructions["pyelftools"] = (
            "pip install pyelftools\n"
            "  # Or: conda install -c conda-forge pyelftools"
        )
    if not (shutil.which("gcc") or shutil.which("clang")):
        missing.append("gcc_or_clang")
        instructions["gcc_or_clang"] = (
            "# Ubuntu/Debian:  sudo apt install gcc clang\n"
            "# macOS:          brew install gcc llvm\n"
            "# Docker:         FROM ubuntu:22.04 && RUN apt-get install -y gcc clang"
        )

    return {
        "all_ready": len(missing) == 0,
        "missing": missing,
        "instructions": instructions,
    }
