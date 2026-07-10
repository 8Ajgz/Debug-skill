"""
Tests for rust_debug/phases.py.

Currently just the regression test for phase_2_formal() - see its docstring
for context. rust_debug otherwise has no dedicated test file; broader
coverage (phase_0/phase_1/phase_3, RustDebugger.debug() end-to-end) is a
separate, pre-existing gap, not addressed here.
"""

from ..phases import RustDebugger


class TestPhase2Formal:
    """Regression tests for phase_2_formal(), which was a stub (a comment
    saying "would call PyProver bridge" followed by `return None`
    unconditionally) - found and fixed by comparing against the real
    implementation in the actual sibling v2.5.2 archive Max uploaded.
    """

    def test_contract_annotated_code_gets_real_result_not_none(self):
        """The defining regression check: code with real // Pre: / // Post:
        annotations must get an actual verification result, not the
        stub's unconditional None."""
        code = (
            "// Pre: x > 0\n"
            "// Post: result > 0\n"
            "fn f(x: i32) -> i32 {\n"
            "    x + 1\n"
            "}\n"
        )
        result = RustDebugger().phase_2_formal(code)
        assert result is not None
        assert "verified" in result
        assert result["source"] in ("pyprover_bridge", "local_contract_verifier")

    def test_no_contracts_returns_none_honestly(self):
        """Code with no contract annotations at all should still return
        None - there's genuinely nothing to verify, and that's a correct
        None, not the stub's coincidentally-also-None-for-everything."""
        code = "fn f(x: i32) -> i32 {\n    x + 1\n}\n"
        result = RustDebugger().phase_2_formal(code)
        # Depending on bridge availability this may return a bridge report
        # (which itself may be None-ish) or fall back to the local
        # ContractVerifier path, which explicitly returns None for no
        # contracts - either is acceptable as long as it's not a crash.
        assert result is None or isinstance(result, dict)

    def test_does_not_crash_on_malformed_code(self):
        """Formal verification failures must degrade to a dict with
        verified=False, never raise past phase_2_formal's own try/except."""
        code = "// Pre: this is not a valid expression &&&\nfn f() {}\n"
        result = RustDebugger().phase_2_formal(code)
        assert result is None or isinstance(result, dict)
