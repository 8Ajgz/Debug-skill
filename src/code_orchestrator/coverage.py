"""Coverage tracking and unified metrics reporting."""

from .type_stubs import (
    CodeStructure,
    CoverageReport,
    ToolCoverage,
    VerificationState,
)


class CoverageTracker:
    """Tracks verification coverage across all tools."""

    def compute(self, state: VerificationState) -> CoverageReport:
        """Compute comprehensive coverage report.
        
        Args:
            state: Current verification state
            
        Returns:
            CoverageReport with all metrics
        """
        functions_percentage = (
            (state.functions_verified / state.functions_total * 100)
            if state.functions_total > 0
            else 0.0
        )

        lines_percentage = (
            (state.lines_verified / state.lines_total * 100)
            if state.lines_total > 0
            else 0.0
        )

        # Compute dependency completeness
        dep_completeness = self._compute_dependency_completeness(state)

        # Compute tool-specific coverage
        by_tool = self._compute_tool_coverage(state)

        # Estimate tokens to complete
        tokens_to_complete = self._estimate_tokens_to_complete(state)

        # Recommend high-value functions
        next_functions = self._get_high_value_functions(state)

        return CoverageReport(
            functions_verified=state.functions_verified,
            functions_total=state.functions_total,
            functions_percentage=functions_percentage,
            lines_verified=state.lines_verified,
            lines_total=state.lines_total,
            lines_percentage=lines_percentage,
            dependency_completeness=dep_completeness,
            by_tool=by_tool,
            pending_functions=state.pending_functions,
            failed_functions=state.failed_functions,
            blocked_functions=state.blocked_functions,
            estimated_tokens_to_complete=tokens_to_complete,
            tokens_remaining=max(0, state.tokens_budget - state.tokens_spent),
            next_high_value_functions=next_functions
        )

    def _compute_dependency_completeness(self, state: VerificationState) -> float:
        """Compute % of dependencies verified for verified functions."""
        if not state.code_structure or not state.verified_functions:
            return 0.0

        total_deps = 0
        verified_deps = 0

        for verified_name in state.verified_functions.keys():
            deps = state.code_structure.dependency_graph.get(verified_name, [])
            total_deps += len(deps)
            verified_deps += sum(1 for d in deps if d in state.verified_functions)

        return (verified_deps / total_deps * 100) if total_deps > 0 else 100.0

    def _compute_tool_coverage(self, state: VerificationState) -> dict:
        """Compute coverage by tool."""
        by_tool = {}

        for tool_name, funcs in state.tools_run.items():
            verified = sum(1 for f in funcs if f in state.verified_functions)
            percentage = (verified / len(funcs) * 100) if funcs else 0.0

            by_tool[tool_name] = ToolCoverage(
                tool_name=tool_name,
                functions_analyzed=len(funcs),
                functions_total=state.functions_total,
                percentage=percentage
            )

        return by_tool

    def _estimate_tokens_to_complete(self, state: VerificationState) -> int:
        """Estimate tokens needed to complete verification."""
        if not state.decomposition_plan or state.functions_verified >= state.functions_total:
            return 0

        remaining_phases = state.decomposition_plan.phases[state.current_phase:]
        return sum(p.estimated_tokens for p in remaining_phases)

    def _get_high_value_functions(self, state: VerificationState, limit: int = 5) -> list:
        """Get high-value functions to verify next.
        
        High value = called by many functions, not yet verified.
        """
        if not state.code_structure:
            return []

        # Score functions by how many other functions depend on them
        scores = {}
        for func in state.code_structure.functions:
            if func.name not in state.verified_functions:
                # Number of callers = importance
                callers = len(func.callers)
                complexity = func.complexity_score
                scores[func.name] = callers * complexity

        # Sort by score descending
        sorted_funcs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [name for name, _ in sorted_funcs[:limit]]
