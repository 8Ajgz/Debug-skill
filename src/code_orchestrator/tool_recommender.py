"""Tool recommender for selecting next verification tool based on state."""

from .types import ToolRecommendation, VerificationState


class ToolRecommender:
    """Recommends which verification tool to use next."""

    # Token costs for each tool
    TOOL_COSTS = {
        "pyprover": 200,          # Formal verification (expensive)
        "python-debug": 150,      # Execution tracing (moderate)
        "test-generator": 100,    # Test synthesis (light)
        "master-debugger": 250,   # Full orchestration (most expensive)
    }

    def recommend_next_tool(self, state: VerificationState) -> ToolRecommendation:
        """Recommend which tool to run next.
        
        Args:
            state: Current verification state
            
        Returns:
            ToolRecommendation with reasoning
        """
        tokens_left = state.tokens_budget - state.tokens_spent
        functions_to_verify = state.get_next_unverified(state.current_phase)

        # If budget is tight, prefer lighter tools
        if tokens_left < 500:
            return ToolRecommendation(
                recommended_tool="test-generator",
                reason="Token budget running low - using lightweight test generation",
                target_functions=functions_to_verify,
                estimated_token_cost=self.TOOL_COSTS["test-generator"],
                expected_benefit="Quick test coverage without heavy verification",
                priority=1
            )

        # If functions are simple (low complexity), use python-debug
        if functions_to_verify:
            avg_complexity = self._get_avg_complexity(state, functions_to_verify)
            if avg_complexity < 5:
                return ToolRecommendation(
                    recommended_tool="python-debug",
                    reason="Simple functions - runtime tracing is efficient",
                    target_functions=functions_to_verify[:5],
                    estimated_token_cost=self.TOOL_COSTS["python-debug"],
                    expected_benefit="Execution traces for simple functions",
                    priority=2
                )

        # For complex functions, use pyprover for formal verification
        if avg_complexity >= 5:
            return ToolRecommendation(
                recommended_tool="pyprover",
                reason="Complex functions - using formal verification",
                target_functions=functions_to_verify[:3],
                estimated_token_cost=self.TOOL_COSTS["pyprover"],
                expected_benefit="Mathematically proven correctness",
                priority=1
            )

        # Default to master-debugger for full analysis
        return ToolRecommendation(
            recommended_tool="master-debugger",
            reason="Full verification phase required",
            target_functions=functions_to_verify[:5],
            estimated_token_cost=self.TOOL_COSTS["master-debugger"],
            expected_benefit="Comprehensive bug detection across all phases",
            priority=3
        )

    def allocate_token_budget(
        self, state: VerificationState, tools: list
    ) -> dict:
        """Allocate token budget across tools.
        
        Args:
            state: Current verification state
            tools: List of tools to use
            
        Returns:
            Dict mapping tool names to token budgets
        """
        tokens_left = state.tokens_budget - state.tokens_spent
        allocation = {}

        # Allocate proportionally to tool cost
        total_cost = sum(self.TOOL_COSTS.get(t, 100) for t in tools)

        for tool in tools:
            cost = self.TOOL_COSTS.get(tool, 100)
            allocation[tool] = int((cost / total_cost) * tokens_left)

        return allocation

    def should_run_tool(self, state: VerificationState, tool: str) -> bool:
        """Check if a tool should be run based on state.
        
        Args:
            state: Current verification state
            tool: Tool name
            
        Returns:
            True if tool should be run
        """
        tokens_needed = self.TOOL_COSTS.get(tool, 100)
        tokens_left = state.tokens_budget - state.tokens_spent

        # Don't run tool if insufficient budget
        if tokens_left < tokens_needed:
            return False

        # Don't run tool if already applied to current functions
        current_funcs = state.get_next_unverified(state.current_phase)
        already_run = state.tools_run.get(tool, [])

        if all(f in already_run for f in current_funcs):
            return False

        return True

    def _get_avg_complexity(self, state: VerificationState, functions: list) -> float:
        """Get average complexity for functions."""
        if not state.code_structure or not functions:
            return 5.0

        complexities = []
        for func_name in functions:
            func = state.code_structure.function_by_name(func_name)
            if func:
                complexities.append(func.complexity_score)

        return sum(complexities) / len(complexities) if complexities else 5.0
