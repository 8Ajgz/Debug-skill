"""
Phase 9: Assembly Dataflow and Taint Analysis

Performs a lightweight intra-procedural dataflow analysis over the CFG
produced by Phase 8. Tracks which registers hold "tainted" (externally
controlled) values and reports when tainted values flow to dangerous
locations: memory writes, indirect branch targets, or system call arguments.

Design rationale:
  Full dataflow analysis requires a complete lattice fixpoint computation.
  This module uses a simpler worklist-based forward dataflow over basic
  blocks — sufficient to catch common taint flows in short functions, and
  realistic to implement without an SMT solver.

Architecture:
  - DataflowState: the abstract state at a program point (set of tainted regs)
  - BlockTransfer: computes how one basic block transforms a DataflowState
  - TaintAnalyzer: worklist fixpoint over the CFG
  - TaintFinding: one reported taint violation

Taint sources (x86-64 calling convention):
  - rdi, rsi, rdx, rcx, r8, r9 — function arguments
  - rax after a call to a read/recv/fgets-like function

Taint sinks (x86-64):
  - [register] or [register+offset] in a write instruction — heap/stack write
  - jmp register — indirect branch
  - syscall with rdi/rsi tainted (system call arguments)

Public API:
    TaintAnalyzer().analyse(cfg, report) → List[TaintFinding]
    DataflowState
    TaintFinding
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from .cfg import BasicBlock, ControlFlowGraph
from .disassembler import AsmInstruction, DisassemblyReport, Arch
from ..common.interop import BugPattern, BugSeverity, ComponentType, LanguageType


# ──────────────────────────────────────────────────────────────────────────────
# Register normalisation (x86-64)
# ──────────────────────────────────────────────────────────────────────────────

# Map every sub-register to its canonical 64-bit name
_REG_CANONICAL: Dict[str, str] = {}

def _build_reg_map() -> None:
    for full, aliases in [
        ("rax", ["eax", "ax", "al", "ah"]),
        ("rbx", ["ebx", "bx", "bl", "bh"]),
        ("rcx", ["ecx", "cx", "cl", "ch"]),
        ("rdx", ["edx", "dx", "dl", "dh"]),
        ("rsi", ["esi", "si", "sil"]),
        ("rdi", ["edi", "di", "dil"]),
        ("rsp", ["esp", "sp", "spl"]),
        ("rbp", ["ebp", "bp", "bpl"]),
        ("r8",  ["r8d", "r8w", "r8b"]),
        ("r9",  ["r9d", "r9w", "r9b"]),
        ("r10", ["r10d","r10w","r10b"]),
        ("r11", ["r11d","r11w","r11b"]),
        ("r12", ["r12d","r12w","r12b"]),
        ("r13", ["r13d","r13w","r13b"]),
        ("r14", ["r14d","r14w","r14b"]),
        ("r15", ["r15d","r15w","r15b"]),
    ]:
        _REG_CANONICAL[full] = full
        for alias in aliases:
            _REG_CANONICAL[alias] = full

_build_reg_map()


def _canonical(reg: str) -> str:
    return _REG_CANONICAL.get(reg.lower().strip(), reg.lower().strip())


# x86-64 argument registers (SysV ABI)
_ARG_REGS_X64: FrozenSet[str] = frozenset(["rdi", "rsi", "rdx", "rcx", "r8", "r9"])

# Registers used in Linux syscall ABI
_SYSCALL_ARG_REGS: FrozenSet[str] = frozenset(["rdi", "rsi", "rdx", "r10", "r8", "r9"])

# Registers whose post-call value is a taint source (return value of read() etc.)
_CALL_RETURN_REGS: FrozenSet[str] = frozenset(["rax"])


# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DataflowState:
    """Abstract state at a program point: set of tainted (canonical) register names."""
    tainted: Set[str] = field(default_factory=set)

    def copy(self) -> "DataflowState":
        return DataflowState(tainted=set(self.tainted))

    def join(self, other: "DataflowState") -> "DataflowState":
        """Merge two states at a join point (union of tainted sets)."""
        return DataflowState(tainted=self.tainted | other.tainted)

    def taint(self, reg: str) -> None:
        self.tainted.add(_canonical(reg))

    def untaint(self, reg: str) -> None:
        self.tainted.discard(_canonical(reg))

    def is_tainted(self, reg: str) -> bool:
        return _canonical(reg) in self.tainted

    def __eq__(self, other: object) -> bool:
        return isinstance(other, DataflowState) and self.tainted == other.tainted


@dataclass
class TaintFinding:
    """One taint violation: a tainted value reached a dangerous sink."""
    sink_type: str          # "memory_write", "indirect_branch", "syscall_arg"
    instruction: str        # human-readable "mnemonic op_str"
    address: int
    tainted_reg: str        # which register carried the taint
    description: str
    severity: BugSeverity = BugSeverity.HIGH
    confidence: float = 0.6

    def to_bug_pattern(self, language: LanguageType = LanguageType.ASSEMBLY) -> BugPattern:
        return BugPattern(
            pattern_type=f"taint_{self.sink_type}",
            severity=self.severity,
            location=f"0x{self.address:x}",
            description=self.description,
            component=ComponentType.CPP_DEBUG,
            language=language,
            suggestion=_TAINT_SUGGESTIONS.get(self.sink_type, "Review data flow from external input."),
            confidence=self.confidence,
        )


_TAINT_SUGGESTIONS: Dict[str, str] = {
    "memory_write": (
        "A register holding externally-controlled data is used as a memory write "
        "destination or offset. Validate and bound-check the value before use."
    ),
    "indirect_branch": (
        "An indirect branch/call target is derived from externally-controlled data. "
        "This is a code-injection / ROP vector. Apply CFI or harden the input validation."
    ),
    "syscall_arg": (
        "A syscall argument is tainted (derived from external input). "
        "Ensure the value is validated before being passed to the kernel."
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Instruction-level transfer function
# ──────────────────────────────────────────────────────────────────────────────

def _parse_operands(op_str: str) -> Tuple[str, str]:
    """Split 'dst, src' operand string. Returns ('', '') on failure."""
    parts = op_str.split(",", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return parts[0].strip() if parts else "", ""


def _is_memory_ref(operand: str) -> bool:
    return "[" in operand


def _extract_regs_from_operand(operand: str) -> List[str]:
    """Extract all register names from an operand string (handles [reg+offset])."""
    import re
    # Match register names: word-boundary, starts with r/e or rN/eN pattern
    tokens = re.findall(r'\b([re][a-z0-9]{1,4}|r\d{1,2}[bdw]?)\b', operand.lower())
    return [_canonical(t) for t in tokens]


def _transfer_instruction(
    insn: AsmInstruction,
    state: DataflowState,
) -> Tuple[DataflowState, List[TaintFinding]]:
    """
    Apply one instruction's transfer function to `state`.

    Returns:
        (new_state, findings_at_this_insn)
    """
    new_state = state.copy()
    findings: List[TaintFinding] = []
    m = insn.mnemonic.lower()
    ops = insn.op_str

    # ── mov family: propagate taint from src to dst ───────────────────────────
    if m.startswith("mov") or m in ("lea", "xchg", "cmov"):
        dst, src = _parse_operands(ops)
        src_regs = _extract_regs_from_operand(src)
        src_tainted = any(new_state.is_tainted(r) for r in src_regs)
        dst_regs = _extract_regs_from_operand(dst)

        if _is_memory_ref(dst) and src_tainted:
            # Tainted value being written to memory
            findings.append(TaintFinding(
                sink_type="memory_write",
                instruction=f"{m} {ops}",
                address=insn.address,
                tainted_reg=next((r for r in src_regs if new_state.is_tainted(r)), "?"),
                description=(
                    f"Tainted value written to memory at 0x{insn.address:x}: "
                    f"{m} {ops}. External input can control memory content."
                ),
                severity=BugSeverity.HIGH,
            ))
        elif _is_memory_ref(dst) and any(new_state.is_tainted(r) for r in _extract_regs_from_operand(dst)):
            # Tainted value used as a memory *address* (even more dangerous)
            findings.append(TaintFinding(
                sink_type="memory_write",
                instruction=f"{m} {ops}",
                address=insn.address,
                tainted_reg=next((r for r in _extract_regs_from_operand(dst) if new_state.is_tainted(r)), "?"),
                description=(
                    f"Tainted register used as memory write address at 0x{insn.address:x}: "
                    f"{m} {ops}. Attacker may control the write target."
                ),
                severity=BugSeverity.CRITICAL,
            ))

        # Propagate: dst register inherits taint from src
        for dst_reg in dst_regs:
            if not _is_memory_ref(dst):
                if src_tainted:
                    new_state.taint(dst_reg)
                else:
                    new_state.untaint(dst_reg)

    # ── arithmetic: taint propagates through ADD/SUB/XOR/AND/OR etc. ─────────
    elif m in ("add", "sub", "xor", "or", "and", "imul", "mul", "shl", "shr", "sar", "rol", "ror"):
        dst, src = _parse_operands(ops)
        src_regs = _extract_regs_from_operand(src)
        dst_regs = _extract_regs_from_operand(dst)
        if any(new_state.is_tainted(r) for r in src_regs + dst_regs):
            for r in dst_regs:
                new_state.taint(r)

    # ── push/pop: track stack taint ───────────────────────────────────────────
    elif m == "push":
        pass  # simplified: don't model stack memory
    elif m == "pop":
        dst_regs = _extract_regs_from_operand(ops)
        # Pop from stack — conservatively untaint (stack could hold anything)
        for r in dst_regs:
            new_state.untaint(r)

    # ── call: function arguments may produce a tainted return value ───────────
    elif m == "call":
        # Conservatively: rax (return value) is tainted after any call if any
        # argument register was tainted.  This over-approximates.
        if any(new_state.is_tainted(r) for r in _ARG_REGS_X64):
            for r in _CALL_RETURN_REGS:
                new_state.taint(r)

    # ── indirect branch ───────────────────────────────────────────────────────
    elif m in ("jmp", "call") and insn.is_indirect:
        jmp_regs = _extract_regs_from_operand(ops)
        for r in jmp_regs:
            if new_state.is_tainted(r):
                findings.append(TaintFinding(
                    sink_type="indirect_branch",
                    instruction=f"{m} {ops}",
                    address=insn.address,
                    tainted_reg=r,
                    description=(
                        f"Indirect branch at 0x{insn.address:x} ({m} {ops}) — "
                        f"target derived from tainted register {r}. "
                        "This is a code-injection / ROP vector."
                    ),
                    severity=BugSeverity.CRITICAL,
                ))

    # ── syscall ───────────────────────────────────────────────────────────────
    elif m == "syscall":
        tainted_args = [r for r in _SYSCALL_ARG_REGS if new_state.is_tainted(r)]
        for r in tainted_args:
            findings.append(TaintFinding(
                sink_type="syscall_arg",
                instruction=f"syscall (arg={r})",
                address=insn.address,
                tainted_reg=r,
                description=(
                    f"Syscall at 0x{insn.address:x} with tainted argument in {r}. "
                    "External input reaches the kernel interface without sanitisation."
                ),
                severity=BugSeverity.HIGH,
            ))

    return new_state, findings


# ──────────────────────────────────────────────────────────────────────────────
# Worklist fixpoint
# ──────────────────────────────────────────────────────────────────────────────

class TaintAnalyzer:
    """
    Forward taint analysis over the CFG.

    Seeds:
      - At the CFG entry, function argument registers (rdi, rsi, rdx, rcx, r8, r9)
        are marked tainted (modelling external input arriving via function arguments).

    Convergence:
      - Runs until no block's output state changes (monotone lattice: tainted set
        grows or stays the same → terminates).

    Usage:
        findings = TaintAnalyzer().analyse(cfg, report)
        patterns = [f.to_bug_pattern() for f in findings]
    """

    MAX_ITERATIONS = 50   # safety limit for large CFGs

    def analyse(
        self,
        cfg: ControlFlowGraph,
        report: Optional[DisassemblyReport] = None,
        language: LanguageType = LanguageType.ASSEMBLY,
    ) -> List[TaintFinding]:
        if cfg.entry_addr is None or not cfg.blocks:
            return []

        # Initial state at entry: argument registers tainted
        entry_state = DataflowState(tainted=set(_ARG_REGS_X64))

        # block_addr → DataflowState at block entry
        block_in: Dict[int, DataflowState] = {cfg.entry_addr: entry_state}
        for addr in cfg.blocks:
            if addr != cfg.entry_addr:
                block_in[addr] = DataflowState()

        all_findings: List[TaintFinding] = []
        worklist = list(cfg.blocks.keys())
        iterations = 0

        while worklist and iterations < self.MAX_ITERATIONS:
            iterations += 1
            addr = worklist.pop(0)
            bb = cfg.blocks[addr]
            in_state = block_in[addr].copy()

            # Apply transfer function for each instruction in the block
            state = in_state
            for insn in bb.instructions:
                state, insn_findings = _transfer_instruction(insn, state)
                all_findings.extend(insn_findings)

            # Propagate out_state to successors; re-add if changed
            for succ_addr in bb.successors:
                if succ_addr not in block_in:
                    block_in[succ_addr] = DataflowState()
                old_in = block_in[succ_addr]
                new_in = old_in.join(state)
                if new_in != old_in:
                    block_in[succ_addr] = new_in
                    if succ_addr not in worklist:
                        worklist.append(succ_addr)

        # Deduplicate: same (sink_type, address)
        seen: Set[Tuple[str, int]] = set()
        deduped: List[TaintFinding] = []
        for f in all_findings:
            key = (f.sink_type, f.address)
            if key not in seen:
                seen.add(key)
                deduped.append(f)

        return deduped
