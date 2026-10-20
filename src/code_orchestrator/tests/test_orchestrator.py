"""CodeOrchestrator end-to-end: analysis, recommendation, reporting, checkpoints.

These cover the public path that failed before the type_stubs merge, where
analyze_codebase() raised TypeError on any input.
"""

import pytest

from ..orchestrator import CodeOrchestrator
from ..types import CoverageReport, OperationErrorType, ToolRecommendation

SOURCE = (
    "def leaf(x):\n"
    "    return x + 1\n"
    "\n"
    "def top(z):\n"
    "    if z > 0:\n"
    "        return leaf(z) * 2\n"
    "    return 0\n"
)


@pytest.fixture
def orchestrator():
    return CodeOrchestrator()


@pytest.fixture
def analysed(orchestrator):
    state, error = orchestrator.analyze_codebase(SOURCE)
    assert error is None, error
    return state


class TestAnalysis:

    def test_analyze_succeeds(self, analysed):
        assert analysed is not None
        assert analysed.code_structure is not None

    def test_functions_found_with_call_graph(self, analysed):
        names = {f.name for f in analysed.code_structure.functions}
        assert names == {"leaf", "top"}
        assert analysed.code_structure.call_graph["top"] == ["leaf"]

    def test_invalid_code_reported_not_raised(self, orchestrator):
        state, error = orchestrator.analyze_codebase("def f(:\n")
        assert state is None
        assert error.error_type == OperationErrorType.INVALID_CODE

    def test_unsupported_language_reported_not_raised(self, orchestrator):
        state, error = orchestrator.analyze_codebase(SOURCE, language="cobol")
        assert state is None
        assert error.error_type == OperationErrorType.UNSUPPORTED_LANGUAGE


class TestRecommendationAndReporting:

    def test_recommend_next_tool(self, orchestrator, analysed):
        rec = orchestrator.recommend_next_tool(analysed)
        assert isinstance(rec, ToolRecommendation)
        assert rec.recommended_tool

    def test_coverage_report_counts_functions(self, orchestrator, analysed):
        report = orchestrator.get_coverage_report(analysed)
        assert isinstance(report, CoverageReport)
        assert report.functions_total == 2
        assert report.functions_verified == 0

    def test_human_readable_report_mentions_progress(self, orchestrator, analysed):
        text = orchestrator.get_human_readable_report(analysed)
        assert "functions" in text.lower()

    def test_summary_mentions_phase(self, orchestrator, analysed):
        assert "Phase" in orchestrator.get_summary(analysed)


class TestCheckpoint:

    def test_round_trip_keeps_project_id(self, orchestrator, analysed):
        checkpoint = orchestrator.get_state_checkpoint(analysed)
        loaded, error = orchestrator.load_checkpoint(checkpoint)
        assert error is None
        assert loaded.project_id == analysed.project_id
        assert loaded.functions_total == analysed.functions_total

    @pytest.mark.xfail(
        strict=True,
        reason="Known gap: VerificationStateIO.serialize() does not write "
               "code_structure or decomposition_plan, so a loaded checkpoint "
               "has no code structure. Remove this marker when fixed.",
    )
    def test_round_trip_keeps_code_structure(self, orchestrator, analysed):
        checkpoint = orchestrator.get_state_checkpoint(analysed)
        loaded, _ = orchestrator.load_checkpoint(checkpoint)
        assert loaded.code_structure is not None
        assert {f.name for f in loaded.code_structure.functions} == {"leaf", "top"}
