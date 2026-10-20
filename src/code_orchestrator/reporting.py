"""Report generation for coverage and verification progress."""

from .types import CoverageReport, VerificationState


class ReportGenerator:
    """Generates human-readable verification reports."""

    @staticmethod
    def generate_coverage_report(report: CoverageReport) -> str:
        """Generate human-readable coverage report.
        
        Args:
            report: CoverageReport object
            
        Returns:
            Formatted string report
        """
        lines = [
            "=" * 70,
            "VERIFICATION COVERAGE REPORT",
            "=" * 70,
            "",
            f"Functions Verified: {report.functions_verified}/{report.functions_total} ({report.functions_percentage:.1f}%)",
            f"Lines Verified:     {report.lines_verified}/{report.lines_total} ({report.lines_percentage:.1f}%)",
            f"Dependency Completeness: {report.dependency_completeness:.1f}%",
            "",
        ]

        if report.by_tool:
            lines.append("Coverage by Tool:")
            for tool_name, coverage in report.by_tool.items():
                lines.append(f"  {tool_name}: {coverage.functions_analyzed} functions ({coverage.percentage:.1f}%)")
            lines.append("")

        if report.pending_functions:
            lines.append(f"Pending Functions ({len(report.pending_functions)}):")
            for func in report.pending_functions[:5]:
                lines.append(f"  - {func}")
            if len(report.pending_functions) > 5:
                lines.append(f"  ... and {len(report.pending_functions) - 5} more")
            lines.append("")

        if report.failed_functions:
            lines.append(f"Failed Functions ({len(report.failed_functions)}):")
            for func, reason in list(report.failed_functions.items())[:3]:
                lines.append(f"  - {func}: {reason}")
            if len(report.failed_functions) > 3:
                lines.append(f"  ... and {len(report.failed_functions) - 3} more")
            lines.append("")

        if report.blocked_functions:
            lines.append(f"Blocked Functions ({len(report.blocked_functions)}):")
            for func in report.blocked_functions[:5]:
                lines.append(f"  - {func}")
            if len(report.blocked_functions) > 5:
                lines.append(f"  ... and {len(report.blocked_functions) - 5} more")
            lines.append("")

        lines.append("Token Usage:")
        lines.append(f"  Remaining: {report.tokens_remaining} tokens")
        lines.append(f"  To Complete: {report.estimated_tokens_to_complete} tokens (estimated)")
        lines.append("")

        if report.next_high_value_functions:
            lines.append("Recommended Next Functions:")
            for func in report.next_high_value_functions:
                lines.append(f"  - {func}")
            lines.append("")

        lines.append("=" * 70)

        return "\n".join(lines)

    @staticmethod
    def generate_next_steps_recommendation(state: VerificationState) -> str:
        """Generate recommendation for next steps.
        
        Args:
            state: VerificationState
            
        Returns:
            Recommendation string
        """
        if state.is_complete():
            return "✓ Verification complete! All functions have been analyzed."

        coverage = state.get_coverage_percentage()
        remaining = state.functions_total - state.functions_verified

        lines = [
            f"Current Progress: {state.functions_verified}/{state.functions_total} functions verified ({coverage:.1f}%)",
            f"Remaining: {remaining} functions",
            "",
        ]

        if state.tokens_spent >= state.tokens_budget:
            lines.append("⚠ Token budget exhausted. Recommend:")
            lines.append(f"  1. Increase token budget by {state.tokens_spent - state.tokens_budget + 2000} tokens")
            lines.append(f"  2. Or deprioritize remaining {remaining} functions")
        else:
            tokens_left = state.tokens_budget - state.tokens_spent
            lines.append(f"✓ {tokens_left} tokens remaining")
            lines.append("")
            lines.append("Next steps:")
            lines.append(f"  1. Run phase {state.current_phase + 1}")
            lines.append(f"  2. Verify {remaining} remaining functions")
            lines.append(f"  3. Save checkpoint and resume in next prompt if needed")

        return "\n".join(lines)

    @staticmethod
    def generate_summary(state: VerificationState) -> str:
        """Generate brief summary.
        
        Args:
            state: VerificationState
            
        Returns:
            Summary string
        """
        coverage = state.get_coverage_percentage()
        status = state.phase_status.value

        return (
            f"Code Orchestrator Verification Summary\n"
            f"Status: {status}\n"
            f"Phase: {state.current_phase}/{len(state.decomposition_plan.phases) if state.decomposition_plan else '?'}\n"
            f"Functions: {state.functions_verified}/{state.functions_total} ({coverage:.1f}%)\n"
            f"Tokens: {state.tokens_spent}/{state.tokens_budget}\n"
            f"Prompts Used: {state.prompts_used}"
        )
