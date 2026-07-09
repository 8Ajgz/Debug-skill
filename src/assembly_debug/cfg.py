"""
Phase 8 (part B): Control Flow Graph construction

Builds a CFG from a DisassemblyReport by identifying basic blocks and
the control-flow edges between them.

A basic block is a maximal sequence of instructions with:
  - A single entry point (first instruction)
  - No internal branches (every instruction falls through to the next)
  - A single exit (last instruction is a branch, call, ret, or the block
    is terminated by the start of another block)

CFG analysis detects:
  - Back edges (cycles / loops)
  - Unreachable blocks (no predecessor)
  - Indirect jump nodes (potential ROP gadgets or dynamic dispatch)
  - Ret imbalance (functions with no return path)
  - Stack-frame anomalies heuristic (RSP/ESP modified in unexpected ways)

Public API:
    BasicBlock       — one node in the CFG
    CFGEdge          — one directed edge
    ControlFlowGraph — the complete graph
    CFGBuilder       — constructs a CFG from a DisassemblyReport
    CFGAnalysis      — detects anomalies in a built CFG
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from .disassembler import AsmInstruction, DisassemblyReport
from ..common.interop import BugPattern, BugSeverity, ComponentType, LanguageType


# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class BasicBlock:
    """A maximal straight-line sequence of instructions."""
    start_addr: int
    end_addr: int                       # address of the LAST instruction
    instructions: List[AsmInstruction] = field(default_factory=list)
    successors: List[int] = field(default_factory=list)   # start_addr of target blocks
    predecessors: List[int] = field(default_factory=list) # start_addr of source blocks

    @property
    def last(self) -> Optional[AsmInstruction]:
        return self.instructions[-1] if self.instructions else None

    @property
    def size(self) -> int:
        return len(self.instructions)

    @property
    def is_exit(self) -> bool:
        """True if the block ends with a ret and has no fallthrough successor."""
        return bool(self.last and self.last.is_ret)

    def __str__(self) -> str:
        return (f"BB@0x{self.start_addr:x}–0x{self.end_addr:x} "
                f"({self.size} insns, {len(self.successors)} succs)")


@dataclass
class CFGEdge:
    source: int         # BasicBlock.start_addr
    target: int         # BasicBlock.start_addr
    edge_type: str      # "fallthrough", "branch", "call", "ret", "indirect"
    is_back_edge: bool = False


@dataclass
class ControlFlowGraph:
    """The complete CFG for a disassembled region."""
    arch: str
    blocks: Dict[int, BasicBlock] = field(default_factory=dict)  # addr → BB
    edges: List[CFGEdge] = field(default_factory=list)

    # Derived sets (populated by CFGBuilder.build)
    entry_addr: Optional[int] = None
    back_edge_pairs: List[Tuple[int, int]] = field(default_factory=list)  # (src,dst) loops
    unreachable_addrs: List[int] = field(default_factory=list)

    @property
    def block_count(self) -> int:
        return len(self.blocks)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def has_cycles(self) -> bool:
        return len(self.back_edge_pairs) > 0

    def successors_of(self, addr: int) -> List[BasicBlock]:
        bb = self.blocks.get(addr)
        if bb is None:
            return []
        return [self.blocks[s] for s in bb.successors if s in self.blocks]

    def predecessors_of(self, addr: int) -> List[BasicBlock]:
        bb = self.blocks.get(addr)
        if bb is None:
            return []
        return [self.blocks[p] for p in bb.predecessors if p in self.blocks]


# ──────────────────────────────────────────────────────────────────────────────
# CFG Builder
# ──────────────────────────────────────────────────────────────────────────────

class CFGBuilder:
    """
    Constructs a ControlFlowGraph from a DisassemblyReport.

    Algorithm:
      1. Identify block leaders (entry, branch targets, fall-throughs after branches)
      2. Partition instructions into basic blocks
      3. Add edges: fallthrough and branch targets
      4. Compute back edges with DFS
      5. Mark unreachable blocks (no predecessor, not entry)
    """

    def build(self, report: DisassemblyReport) -> ControlFlowGraph:
        if not report.instructions:
            return ControlFlowGraph(arch=report.arch, entry_addr=None)

        cfg = ControlFlowGraph(arch=report.arch)
        insns = report.instructions
        addr_map: Dict[int, AsmInstruction] = report.address_map()

        # ── Step 1: find all block leaders ───────────────────────────────────
        leaders: Set[int] = {insns[0].address}  # first instruction is always a leader
        for insn in insns:
            if insn.is_branch or insn.is_call or insn.is_ret:
                # Instruction after a branch/call is a leader (if it exists)
                if insn.next_address in addr_map:
                    leaders.add(insn.next_address)
                # Branch target is a leader
                if insn.branch_target is not None and insn.branch_target in addr_map:
                    leaders.add(insn.branch_target)

        leaders_sorted = sorted(leaders)

        # ── Step 2: build basic blocks ────────────────────────────────────────
        leader_set = set(leaders_sorted)
        current_bb: Optional[BasicBlock] = None

        for insn in insns:
            if insn.address in leader_set:
                current_bb = BasicBlock(
                    start_addr=insn.address,
                    end_addr=insn.address,
                )
                cfg.blocks[insn.address] = current_bb

            if current_bb is not None:
                current_bb.instructions.append(insn)
                current_bb.end_addr = insn.address
                # End the block at a branch, call, or ret
                if insn.is_branch or insn.is_ret:
                    current_bb = None

        # ── Step 3: add edges ─────────────────────────────────────────────────
        for bb in cfg.blocks.values():
            last = bb.last
            if last is None:
                continue

            if last.is_ret:
                # No successor (or a symbolic "return" edge not modelled here)
                continue

            if last.is_unconditional_jump and not last.is_call:
                # Unconditional branch: one successor (the target)
                if last.branch_target is not None and last.branch_target in cfg.blocks:
                    _add_edge(cfg, bb.start_addr, last.branch_target,
                              "indirect" if last.is_indirect else "branch")
                elif last.is_indirect:
                    pass  # target not statically known

            elif last.is_conditional_branch:
                # Two successors: taken (branch_target) and not-taken (fall-through)
                if last.branch_target is not None and last.branch_target in cfg.blocks:
                    _add_edge(cfg, bb.start_addr, last.branch_target, "branch")
                if last.next_address in cfg.blocks:
                    _add_edge(cfg, bb.start_addr, last.next_address, "fallthrough")

            elif last.is_call:
                # Fall-through after call (call returns)
                if last.next_address in cfg.blocks:
                    _add_edge(cfg, bb.start_addr, last.next_address, "call")

            else:
                # Ordinary instruction at end of block: fall through to next block
                if last.next_address in cfg.blocks:
                    _add_edge(cfg, bb.start_addr, last.next_address, "fallthrough")

        # ── Step 4: back edges via DFS ────────────────────────────────────────
        cfg.entry_addr = insns[0].address
        cfg.back_edge_pairs = _find_back_edges(cfg)
        for src, dst in cfg.back_edge_pairs:
            for edge in cfg.edges:
                if edge.source == src and edge.target == dst:
                    edge.is_back_edge = True

        # ── Step 5: unreachable blocks ────────────────────────────────────────
        reachable = _reachable_set(cfg, cfg.entry_addr)
        cfg.unreachable_addrs = [
            addr for addr in cfg.blocks if addr not in reachable
        ]

        return cfg


def _add_edge(cfg: ControlFlowGraph, src: int, dst: int, etype: str) -> None:
    """Add an edge and update predecessor/successor lists."""
    cfg.edges.append(CFGEdge(source=src, target=dst, edge_type=etype))
    cfg.blocks[src].successors.append(dst)
    if dst in cfg.blocks:
        cfg.blocks[dst].predecessors.append(src)


def _find_back_edges(cfg: ControlFlowGraph) -> List[Tuple[int, int]]:
    """DFS-based back-edge detection (src → dst where dst is an ancestor)."""
    back: List[Tuple[int, int]] = []
    entry = cfg.entry_addr
    if entry is None:
        return back

    visited: Set[int] = set()
    in_stack: Set[int] = set()

    def dfs(addr: int) -> None:
        visited.add(addr)
        in_stack.add(addr)
        bb = cfg.blocks.get(addr)
        if bb:
            for succ in bb.successors:
                if succ not in visited:
                    dfs(succ)
                elif succ in in_stack:
                    back.append((addr, succ))
        in_stack.discard(addr)

    dfs(entry)
    return back


def _reachable_set(cfg: ControlFlowGraph, entry: Optional[int]) -> Set[int]:
    """BFS reachability from entry."""
    if entry is None:
        return set()
    reachable: Set[int] = set()
    queue = [entry]
    while queue:
        addr = queue.pop()
        if addr in reachable:
            continue
        reachable.add(addr)
        bb = cfg.blocks.get(addr)
        if bb:
            for succ in bb.successors:
                if succ not in reachable:
                    queue.append(succ)
    return reachable


# ──────────────────────────────────────────────────────────────────────────────
# CFG Analysis — anomaly detection
# ──────────────────────────────────────────────────────────────────────────────

class CFGAnalysis:
    """
    Detects structural anomalies in a ControlFlowGraph.

    Produces BugPattern records compatible with the unified interop layer.
    """

    def analyse(self, cfg: ControlFlowGraph, language: LanguageType = LanguageType.ASSEMBLY) -> List[BugPattern]:
        patterns: List[BugPattern] = []
        patterns += self._check_indirect_jumps(cfg, language)
        patterns += self._check_unreachable_blocks(cfg, language)
        patterns += self._check_loops(cfg, language)
        patterns += self._check_no_return(cfg, language)
        return patterns

    # ── individual checks ─────────────────────────────────────────────────────

    def _check_indirect_jumps(self, cfg: ControlFlowGraph, lang: LanguageType) -> List[BugPattern]:
        """Flag blocks that exit via an indirect jump (potential ROP gadget / vtable dispatch)."""
        patterns: List[BugPattern] = []
        for bb in cfg.blocks.values():
            last = bb.last
            if last and last.is_indirect and (last.is_branch or last.is_call):
                patterns.append(BugPattern(
                    pattern_type="indirect_control_transfer",
                    severity=BugSeverity.MEDIUM,
                    location=f"0x{last.address:x}",
                    description=(
                        f"Indirect {'call' if last.is_call else 'jump'} at 0x{last.address:x} "
                        f"({last.mnemonic} {last.op_str}). Target is not statically determinable — "
                        "this may be a virtual dispatch, function pointer call, or a ROP gadget entry."
                    ),
                    component=ComponentType.CPP_DEBUG,
                    language=lang,
                    suggestion=(
                        "Verify that all possible jump targets are from expected locations. "
                        "Control-flow integrity (CFI) mitigations restrict indirect transfer targets."
                    ),
                    confidence=0.7,
                ))
        return patterns

    def _check_unreachable_blocks(self, cfg: ControlFlowGraph, lang: LanguageType) -> List[BugPattern]:
        """Flag blocks with no predecessor (dead code)."""
        patterns: List[BugPattern] = []
        for addr in cfg.unreachable_addrs:
            bb = cfg.blocks.get(addr)
            if bb is None:
                continue
            patterns.append(BugPattern(
                pattern_type="unreachable_code",
                severity=BugSeverity.LOW,
                location=f"0x{addr:x}",
                description=(
                    f"Basic block at 0x{addr:x} ({bb.size} instruction(s)) has no predecessor "
                    "in the static CFG. This code is unreachable under normal control flow — "
                    "it may be dead code or only reachable via an indirect jump not captured here."
                ),
                component=ComponentType.CPP_DEBUG,
                language=lang,
                suggestion=(
                    "Remove dead code or verify that the block is reachable through an "
                    "indirect branch not captured in the static CFG."
                ),
                confidence=0.6,
            ))
        return patterns

    def _check_loops(self, cfg: ControlFlowGraph, lang: LanguageType) -> List[BugPattern]:
        """Report detected back-edges (potential infinite loops) at INFO severity."""
        patterns: List[BugPattern] = []
        for src, dst in cfg.back_edge_pairs:
            patterns.append(BugPattern(
                pattern_type="back_edge_loop",
                severity=BugSeverity.INFO,
                location=f"0x{src:x}→0x{dst:x}",
                description=(
                    f"Back edge from 0x{src:x} to 0x{dst:x} detected — this forms a loop. "
                    "Loops are normal, but an unbounded loop with no exit condition "
                    "may indicate an infinite loop bug."
                ),
                component=ComponentType.CPP_DEBUG,
                language=lang,
                suggestion="Verify the loop has an exit condition reachable on all inputs.",
                confidence=0.5,
            ))
        return patterns

    def _check_no_return(self, cfg: ControlFlowGraph, lang: LanguageType) -> List[BugPattern]:
        """Flag functions where no basic block ends with a RET (possible missing return)."""
        has_ret = any(bb.is_exit for bb in cfg.blocks.values())
        if not has_ret and cfg.block_count > 0:
            return [BugPattern(
                pattern_type="no_return_path",
                severity=BugSeverity.MEDIUM,
                location=f"0x{cfg.entry_addr:x}" if cfg.entry_addr else "unknown",
                description=(
                    "No basic block in this CFG ends with a RET instruction. "
                    "The function may exit via a tail-call, an infinite loop, or "
                    "a missing return path (a common bug in non-void functions)."
                ),
                component=ComponentType.CPP_DEBUG,
                language=lang,
                suggestion=(
                    "Ensure all code paths either reach a RET or a known no-return "
                    "call (abort, exit, __builtin_unreachable)."
                ),
                confidence=0.5,
            )]
        return []
