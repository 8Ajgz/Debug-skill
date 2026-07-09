"""
Phase 8 (part A): Assembly Disassembler using Capstone

Disassembles raw machine code bytes or ELF binaries into structured
AsmInstruction records, classifying each instruction as a branch, call,
return, indirect, or ordinary instruction.

Input modes:
  - disassemble_bytes(data, arch, base_addr)  → List[AsmInstruction]
  - Disassembler().from_bytes(...)             → DisassemblyReport
  - Disassembler().from_binary(path, arch)    → DisassemblyReport (reads .text section)

Supported architectures (via Capstone):
  - x86_64 (default), x86_32, arm, arm64

Degrades gracefully when Capstone is not installed.

Public API:
    AsmInstruction    — one decoded instruction
    DisassemblyReport — full result of disassembling a buffer or binary
    Disassembler      — main entry point
    capstone_available() → bool
"""

import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    import capstone
    from capstone import x86_const, arm_const, arm64_const
    _CAPSTONE_OK = True
except ImportError:
    _CAPSTONE_OK = False

try:
    from elftools.elf.elffile import ELFFile
    _ELFTOOLS_OK = True
except ImportError:
    _ELFTOOLS_OK = False


# ──────────────────────────────────────────────────────────────────────────────
# Availability
# ──────────────────────────────────────────────────────────────────────────────

def capstone_available() -> bool:
    return _CAPSTONE_OK


# ──────────────────────────────────────────────────────────────────────────────
# Architecture registry
# ──────────────────────────────────────────────────────────────────────────────

class Arch:
    X86_64 = "x86_64"
    X86_32 = "x86_32"
    ARM    = "arm"
    ARM64  = "arm64"

    _CS_PARAMS: Dict[str, Tuple] = {
        "x86_64": ("CS_ARCH_X86",  "CS_MODE_64"),
        "x86_32": ("CS_ARCH_X86",  "CS_MODE_32"),
        "arm":    ("CS_ARCH_ARM",  "CS_MODE_ARM"),
        "arm64":  ("CS_ARCH_ARM64","CS_MODE_ARM"),
    }

    @classmethod
    def cs_params(cls, arch: str) -> Optional[Tuple]:
        """Return (cs_arch, cs_mode) int constants for a named arch."""
        if not _CAPSTONE_OK:
            return None
        params = cls._CS_PARAMS.get(arch)
        if params is None:
            return None
        cs_arch = getattr(capstone, params[0], None)
        cs_mode = getattr(capstone, params[1], None)
        if cs_arch is None or cs_mode is None:
            return None
        return cs_arch, cs_mode

    @classmethod
    def from_elf_machine(cls, machine: str) -> str:
        """Guess arch string from ELF e_machine field."""
        m = machine.upper()
        if "X86_64" in m or "AMD64" in m or "EM_X86_64" in m:
            return cls.X86_64
        if "386" in m or "EM_386" in m:
            return cls.X86_32
        if "AARCH64" in m or "EM_AARCH64" in m:
            return cls.ARM64
        if "ARM" in m or "EM_ARM" in m:
            return cls.ARM
        return cls.X86_64  # default


# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class AsmInstruction:
    """One decoded assembly instruction."""
    address: int
    mnemonic: str
    op_str: str
    size: int                           # bytes
    raw_bytes: bytes

    # Classification flags
    is_branch: bool = False             # conditional or unconditional jump
    is_unconditional_jump: bool = False # JMP / B (ARM) — always taken
    is_conditional_branch: bool = False # JE/JNE/… — taken if condition holds
    is_call: bool = False               # CALL / BL
    is_ret: bool = False                # RET / BX LR
    is_indirect: bool = False           # branch target in register or memory

    # Branch target (if statically determinable)
    branch_target: Optional[int] = None

    @property
    def next_address(self) -> int:
        return self.address + self.size

    def __str__(self) -> str:
        return f"0x{self.address:08x}: {self.mnemonic:<8s} {self.op_str}"


@dataclass
class DisassemblyReport:
    """Full disassembly result for a buffer or ELF binary."""
    arch: str
    base_addr: int
    instructions: List[AsmInstruction] = field(default_factory=list)
    tool_available: bool = True
    error: str = ""

    # Summary statistics
    @property
    def instruction_count(self) -> int:
        return len(self.instructions)

    @property
    def branch_count(self) -> int:
        return sum(1 for i in self.instructions if i.is_branch)

    @property
    def call_count(self) -> int:
        return sum(1 for i in self.instructions if i.is_call)

    @property
    def indirect_count(self) -> int:
        return sum(1 for i in self.instructions if i.is_indirect)

    @property
    def ret_count(self) -> int:
        return sum(1 for i in self.instructions if i.is_ret)

    def at_address(self, addr: int) -> Optional[AsmInstruction]:
        """Return the instruction at exactly `addr`, or None."""
        for insn in self.instructions:
            if insn.address == addr:
                return insn
        return None

    def address_map(self) -> Dict[int, AsmInstruction]:
        return {i.address: i for i in self.instructions}


# ──────────────────────────────────────────────────────────────────────────────
# Instruction classification helpers
# ──────────────────────────────────────────────────────────────────────────────

# x86/x64 mnemonic prefixes for each class
_X86_UNCOND_JUMP = {"jmp"}
_X86_COND_BRANCH = {
    "je","jne","jz","jnz","jl","jle","jg","jge","ja","jae","jb","jbe",
    "js","jns","jo","jno","jp","jnp","jpe","jpo","jcxz","jecxz","jrcxz",
    "loop","loope","loopne",
}
_X86_CALL = {"call"}
_X86_RET  = {"ret","retf","retn","iret","iretd","iretq"}

_ARM_UNCOND = {"b","bl","bx","blx","br","blr"}
_ARM_COND   = {
    "beq","bne","blt","ble","bgt","bge","blo","bls","bhi","bhs",
    "bcs","bcc","bmi","bpl","bvs","bvc","bls",
}
_ARM_RET = {"bx", "ret"}  # BX LR / RET


def _classify_x86(insn: "capstone.CsInsn") -> dict:
    m = insn.mnemonic.lower().split()[0]
    ops = insn.op_str.lower()
    is_indirect = any(c in ops for c in ("[", "r", "e")) if m in (_X86_UNCOND_JUMP | _X86_CALL) else False
    target = None
    if not is_indirect:
        try:
            target = int(insn.op_str, 16)
        except (ValueError, TypeError):
            pass
    return {
        "is_branch": m in _X86_UNCOND_JUMP | _X86_COND_BRANCH,
        "is_unconditional_jump": m in _X86_UNCOND_JUMP,
        "is_conditional_branch": m in _X86_COND_BRANCH,
        "is_call": m in _X86_CALL,
        "is_ret": m in _X86_RET,
        "is_indirect": is_indirect,
        "branch_target": target,
    }


def _classify_arm(insn: "capstone.CsInsn") -> dict:
    m = insn.mnemonic.lower()
    base = m.rstrip("eq ne lt le gt ge lo ls hi hs cs cc mi pl vs vc".split())
    # Indirect = register operand in branch/call
    ops = insn.op_str.lower()
    is_indirect = bool(ops and not ops.startswith("#") and not ops.startswith("0x"))
    target = None
    if not is_indirect:
        try:
            target = int(insn.op_str.lstrip("#"), 16)
        except (ValueError, TypeError):
            pass
    is_uncond = m in _ARM_UNCOND
    is_cond   = any(m.startswith(b) for b in _ARM_COND)
    is_ret    = ("bx" in m and "lr" in ops) or m == "ret"
    return {
        "is_branch": is_uncond or is_cond,
        "is_unconditional_jump": is_uncond and not m.startswith("bl"),
        "is_conditional_branch": is_cond,
        "is_call": m.startswith("bl") and not is_ret,
        "is_ret": is_ret,
        "is_indirect": is_indirect,
        "branch_target": target,
    }


def _classify_instruction(insn: "capstone.CsInsn", arch: str) -> dict:
    if arch in (Arch.X86_64, Arch.X86_32):
        return _classify_x86(insn)
    return _classify_arm(insn)


# ──────────────────────────────────────────────────────────────────────────────
# Disassembler
# ──────────────────────────────────────────────────────────────────────────────

class Disassembler:
    """
    Disassembles machine code using Capstone.

    Usage:
        report = Disassembler().from_bytes(raw_bytes, arch="x86_64", base_addr=0x1000)
        report = Disassembler().from_binary("/path/to/elf")
    """

    def from_bytes(
        self,
        data: bytes,
        arch: str = Arch.X86_64,
        base_addr: int = 0x1000,
    ) -> DisassemblyReport:
        """
        Disassemble a raw byte sequence.

        Args:
            data:      raw machine code bytes
            arch:      "x86_64" (default), "x86_32", "arm", "arm64"
            base_addr: virtual address to assign to the first byte
        """
        if not _CAPSTONE_OK:
            return DisassemblyReport(
                arch=arch, base_addr=base_addr,
                tool_available=False, error="capstone not installed",
            )

        params = Arch.cs_params(arch)
        if params is None:
            return DisassemblyReport(
                arch=arch, base_addr=base_addr,
                tool_available=False, error=f"Unsupported arch: {arch}",
            )

        cs_arch, cs_mode = params
        md = capstone.Cs(cs_arch, cs_mode)
        md.detail = True

        report = DisassemblyReport(arch=arch, base_addr=base_addr)
        try:
            for cs_insn in md.disasm(data, base_addr):
                classification = _classify_instruction(cs_insn, arch)
                insn = AsmInstruction(
                    address=cs_insn.address,
                    mnemonic=cs_insn.mnemonic,
                    op_str=cs_insn.op_str,
                    size=cs_insn.size,
                    raw_bytes=bytes(cs_insn.bytes),
                    **classification,
                )
                report.instructions.append(insn)
        except Exception as exc:
            report.error = f"Disassembly error: {exc}"

        return report

    def from_binary(self, path: str, arch: Optional[str] = None) -> DisassemblyReport:
        """
        Read the .text section of an ELF binary and disassemble it.

        If `arch` is None, auto-detects from the ELF header via pyelftools
        (falls back to x86_64 if pyelftools is unavailable).
        """
        if not _CAPSTONE_OK:
            return DisassemblyReport(
                arch=arch or Arch.X86_64, base_addr=0,
                tool_available=False, error="capstone not installed",
            )

        p = Path(path)
        if not p.exists():
            return DisassemblyReport(
                arch=arch or Arch.X86_64, base_addr=0,
                tool_available=False, error=f"File not found: {path}",
            )

        detected_arch = arch
        text_data: Optional[bytes] = None
        base_addr = 0

        if _ELFTOOLS_OK:
            try:
                with open(path, "rb") as f:
                    elf = ELFFile(f)
                    if detected_arch is None:
                        detected_arch = Arch.from_elf_machine(str(elf.header.e_machine))
                    text_sec = elf.get_section_by_name(".text")
                    if text_sec is not None:
                        text_data = text_sec.data()
                        base_addr = text_sec.header.sh_addr
            except Exception as exc:
                return DisassemblyReport(
                    arch=detected_arch or Arch.X86_64, base_addr=0,
                    tool_available=True, error=f"ELF parsing failed: {exc}",
                )
        else:
            # Fall back: read whole file (will produce garbage after non-code sections,
            # but still useful for quick inspection)
            text_data = p.read_bytes()
            detected_arch = detected_arch or Arch.X86_64

        if text_data is None or len(text_data) == 0:
            return DisassemblyReport(
                arch=detected_arch, base_addr=0,
                tool_available=True, error="No .text section found in binary",
            )

        return self.from_bytes(text_data, arch=detected_arch, base_addr=base_addr)


# ──────────────────────────────────────────────────────────────────────────────
# Setup helper
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_TOOLS = {
    "capstone": {
        "description": "Disassembly framework supporting x86, ARM, MIPS, etc.",
        "check": "python3 -c \"import capstone; print(capstone.version_bind())\"",
        "install": {
            "pip": "pip install capstone",
            "conda": "conda install -c conda-forge capstone",
        },
        "optional": False,
    },
    "pyelftools": {
        "description": "ELF parser for reading binary .text sections (optional; falls back to raw bytes)",
        "check": "python3 -c \"from elftools.elf.elffile import ELFFile; print('ok')\"",
        "install": {"pip": "pip install pyelftools"},
        "optional": True,
    },
}


def disasm_check_and_install() -> dict:
    missing, instructions = [], {}
    if not _CAPSTONE_OK:
        missing.append("capstone")
        instructions["capstone"] = "pip install capstone"
    if not _ELFTOOLS_OK:
        missing.append("pyelftools (optional)")
        instructions["pyelftools"] = "pip install pyelftools"
    return {"all_ready": not missing, "missing": missing, "instructions": instructions}
