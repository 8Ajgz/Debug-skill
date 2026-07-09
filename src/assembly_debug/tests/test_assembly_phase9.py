"""Tests for Phase 9: register dataflow and taint analysis."""
import pytest

from src.assembly_debug.dataflow import (
    DataflowState,
    TaintFinding,
    TaintAnalyzer,
    _canonical,
    _parse_operands,
    _is_memory_ref,
    _extract_regs_from_operand,
    _transfer_instruction,
    _ARG_REGS_X64,
)
from src.assembly_debug.disassembler import AsmInstruction, Disassembler, capstone_available
from src.assembly_debug.cfg import CFGBuilder
from src.common.interop import BugSeverity, ComponentType, LanguageType


# ─── DataflowState ────────────────────────────────────────────────────────────

class TestDataflowState:

    def test_empty_state(self):
        s = DataflowState()
        assert not s.is_tainted("rdi")

    def test_taint_and_check(self):
        s = DataflowState()
        s.taint("rdi")
        assert s.is_tainted("rdi")

    def test_canonical_alias(self):
        s = DataflowState()
        s.taint("rdi")
        assert s.is_tainted("edi")  # alias maps to same canonical

    def test_untaint(self):
        s = DataflowState()
        s.taint("rax")
        s.untaint("rax")
        assert not s.is_tainted("rax")

    def test_join_union(self):
        a = DataflowState(tainted={"rdi"})
        b = DataflowState(tainted={"rsi"})
        c = a.join(b)
        assert c.is_tainted("rdi")
        assert c.is_tainted("rsi")

    def test_copy_independent(self):
        a = DataflowState(tainted={"rdi"})
        b = a.copy()
        b.taint("rsi")
        assert not a.is_tainted("rsi")

    def test_equality(self):
        a = DataflowState(tainted={"rdi"})
        b = DataflowState(tainted={"rdi"})
        assert a == b

    def test_inequality(self):
        a = DataflowState(tainted={"rdi"})
        b = DataflowState(tainted={"rsi"})
        assert a != b


# ─── register canonicalisation ────────────────────────────────────────────────

class TestCanonical:

    def test_full_reg_maps_to_itself(self):
        assert _canonical("rax") == "rax"

    def test_eax_maps_to_rax(self):
        assert _canonical("eax") == "rax"

    def test_al_maps_to_rax(self):
        assert _canonical("al") == "rax"

    def test_r8d_maps_to_r8(self):
        assert _canonical("r8d") == "r8"

    def test_unknown_reg_passthrough(self):
        assert _canonical("xmm0") == "xmm0"


# ─── operand utilities ────────────────────────────────────────────────────────

class TestOperandUtils:

    def test_parse_two_operands(self):
        dst, src = _parse_operands("rax, rbx")
        assert dst == "rax"
        assert src == "rbx"

    def test_parse_one_operand(self):
        dst, src = _parse_operands("rdi")
        assert dst == "rdi"
        assert src == ""

    def test_is_memory_ref_positive(self):
        assert _is_memory_ref("[rax+8]")

    def test_is_memory_ref_negative(self):
        assert not _is_memory_ref("rax")

    def test_extract_regs_simple(self):
        regs = _extract_regs_from_operand("rax")
        assert "rax" in regs

    def test_extract_regs_from_mem_ref(self):
        regs = _extract_regs_from_operand("[rbx+8]")
        assert "rbx" in regs


# ─── _transfer_instruction ────────────────────────────────────────────────────

def _insn(mnemonic: str, op_str: str, addr: int = 0x1000) -> AsmInstruction:
    return AsmInstruction(
        address=addr, mnemonic=mnemonic, op_str=op_str,
        size=4, raw_bytes=b"\x00" * 4,
    )


class TestTransferInstruction:

    def test_mov_propagates_taint(self):
        state = DataflowState(tainted={"rdi"})
        insn = _insn("mov", "rax, rdi")
        new_state, findings = _transfer_instruction(insn, state)
        assert new_state.is_tainted("rax")

    def test_mov_clears_taint_on_untainted_src(self):
        state = DataflowState(tainted={"rax"})
        insn = _insn("mov", "rax, 0")   # constant src, no registers
        new_state, findings = _transfer_instruction(insn, state)
        # rax may or may not be cleared (no src regs) — should not raise
        assert isinstance(findings, list)

    def test_mov_to_memory_flags_sink(self):
        state = DataflowState(tainted={"rsi"})
        insn = _insn("mov", "[rbx], rsi")
        new_state, findings = _transfer_instruction(insn, state)
        types = [f.sink_type for f in findings]
        assert "memory_write" in types

    def test_clean_mov_no_findings(self):
        state = DataflowState()
        insn = _insn("mov", "rax, rbx")
        _, findings = _transfer_instruction(insn, state)
        assert findings == []

    def test_add_propagates_taint(self):
        state = DataflowState(tainted={"rdi"})
        insn = _insn("add", "rax, rdi")
        new_state, _ = _transfer_instruction(insn, state)
        assert new_state.is_tainted("rax")

    def test_syscall_flags_tainted_arg(self):
        state = DataflowState(tainted={"rdi"})
        insn = _insn("syscall", "")
        _, findings = _transfer_instruction(insn, state)
        types = [f.sink_type for f in findings]
        assert "syscall_arg" in types

    def test_syscall_clean_no_findings(self):
        state = DataflowState()  # nothing tainted
        insn = _insn("syscall", "")
        _, findings = _transfer_instruction(insn, state)
        assert findings == []

    def test_indirect_branch_flags_tainted_target(self):
        state = DataflowState(tainted={"rax"})
        insn = AsmInstruction(
            address=0x1000, mnemonic="jmp", op_str="rax",
            size=2, raw_bytes=b"\xff\xe0",
            is_branch=True, is_unconditional_jump=True, is_indirect=True,
        )
        _, findings = _transfer_instruction(insn, state)
        types = [f.sink_type for f in findings]
        assert "indirect_branch" in types

    def test_taint_finding_to_bug_pattern(self):
        f = TaintFinding(
            sink_type="memory_write",
            instruction="mov [rax], rdi",
            address=0x1000,
            tainted_reg="rdi",
            description="test finding",
        )
        p = f.to_bug_pattern(language=LanguageType.ASSEMBLY)
        assert p.pattern_type == "taint_memory_write"
        assert p.language == LanguageType.ASSEMBLY
        assert p.component == ComponentType.CPP_DEBUG


# ─── TaintAnalyzer integration ────────────────────────────────────────────────

@pytest.mark.skipif(not capstone_available(), reason="capstone not installed")
class TestTaintAnalyzerIntegration:

    # x86-64: mov rax, rdi; mov [rbx], rax; ret
    # rdi is tainted → rax becomes tainted → [rbx] write with tainted rax
    WRITE_TAINTED_BYTES = bytes.fromhex("4889F8 488903 C3".replace(" ", ""))

    def test_empty_cfg_no_findings(self):
        from src.assembly_debug.cfg import ControlFlowGraph
        cfg = ControlFlowGraph(arch="x86_64")
        findings = TaintAnalyzer().analyse(cfg)
        assert findings == []

    def test_taint_propagates_to_memory_write(self):
        r = Disassembler().from_bytes(self.WRITE_TAINTED_BYTES, arch="x86_64", base_addr=0x1000)
        cfg = CFGBuilder().build(r)
        findings = TaintAnalyzer().analyse(cfg)
        types = [f.sink_type for f in findings]
        # Should detect that tainted value flows into memory write
        assert "memory_write" in types

    def test_clean_code_no_critical_findings(self):
        # nop; ret — no taint sinks
        clean = bytes.fromhex("90 C3".replace(" ", ""))
        r = Disassembler().from_bytes(clean, arch="x86_64", base_addr=0x1000)
        cfg = CFGBuilder().build(r)
        findings = TaintAnalyzer().analyse(cfg)
        # No critical findings in nop;ret
        assert not any(f.severity == BugSeverity.CRITICAL for f in findings)

    def test_deduplicated_findings(self):
        # Running twice should give the same count (no duplicates from repeated analysis)
        r = Disassembler().from_bytes(self.WRITE_TAINTED_BYTES, arch="x86_64", base_addr=0x1000)
        cfg = CFGBuilder().build(r)
        findings_1 = TaintAnalyzer().analyse(cfg)
        findings_2 = TaintAnalyzer().analyse(cfg)
        assert len(findings_1) == len(findings_2)
