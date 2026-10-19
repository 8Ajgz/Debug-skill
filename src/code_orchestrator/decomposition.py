"""Decomposition planner for breaking code into verification phases."""

from typing import Dict, List, Set

from .type_stubs import CodeStructure, DecompositionPlan, VerificationPhase


class DecompositionPlanner:
    """Plans verification phases using multiple strategies."""

    # Token cost estimates per function
    TOKENS_PER_FUNCTION = 150  # Base estimate
    COMPLEXITY_MULTIPLIER = {
        "simple": 1.0,
        "moderate": 1.5,
        "complex": 2.5
    }

    def plan(
        self,
        code_structure: CodeStructure,
        strategy: str = "topological_sort",
        token_budget: int = 5000
    ) -> DecompositionPlan:
        """Create a decomposition plan.
        
        Args:
            code_structure: Code structure to decompose
            strategy: Decomposition strategy
            token_budget: Token budget for verification
            
        Returns:
            DecompositionPlan with phases
        """
        if strategy == "topological_sort":
            phases = self._topological_sort_phases(code_structure)
        elif strategy == "leaf_first":
            phases = self._leaf_first_phases(code_structure)
        elif strategy == "complexity_ascending":
            phases = self._complexity_ascending_phases(code_structure)
        elif strategy == "module_scoped":
            phases = self._module_scoped_phases(code_structure)
        else:
            phases = self._topological_sort_phases(code_structure)

        # Calculate token costs and complexity levels
        for i, phase in enumerate(phases):
            cost = self._estimate_phase_cost(phase.target_functions, code_structure)
            phase.estimated_tokens = cost
            phase.complexity_level = self._assess_complexity(phase.target_functions, code_structure)
            phase.preconditions = [f"phase_{j}_verified" for j in range(i)]

        # Calculate total cost
        total_tokens = sum(p.estimated_tokens for p in phases)

        # Warn if over budget
        if total_tokens > token_budget:
            # Merge later phases to fit budget
            phases = self._merge_phases_to_budget(phases, token_budget)

        return DecompositionPlan(
            phases=phases,
            total_functions=len(code_structure.functions),
            total_lines=code_structure.total_lines,
            estimated_total_tokens=sum(p.estimated_tokens for p in phases),
            strategy=strategy
        )

    def _topological_sort_phases(self, code_structure: CodeStructure) -> List[VerificationPhase]:
        """Create phases using topological sort (dependencies first)."""
        phases = []
        verified: Set[str] = set()
        phase_num = 0

        while len(verified) < len(code_structure.functions):
            # Find functions with all dependencies verified
            ready = []
            for func in code_structure.functions:
                if func.name not in verified:
                    deps = code_structure.dependency_graph.get(func.name, [])
                    if all(d in verified for d in deps):
                        ready.append(func.name)

            if not ready:
                # Circular dependency - break it
                ready = [f.name for f in code_structure.functions if f.name not in verified][:1]

            phase = VerificationPhase(
                phase_number=phase_num,
                target_functions=ready,
                estimated_tokens=0,
                reason=f"Functions with all dependencies verified (topological sort)"
            )
            phases.append(phase)

            verified.update(ready)
            phase_num += 1

        return phases

    def _leaf_first_phases(self, code_structure: CodeStructure) -> List[VerificationPhase]:
        """Create phases with leaf functions (no callees) first."""
        phases = []
        verified: Set[str] = set()

        # Find leaf functions (no outgoing calls)
        leaves = [
            f.name for f in code_structure.functions
            if not code_structure.call_graph.get(f.name, [])
        ]

        if leaves:
            phase = VerificationPhase(
                phase_number=0,
                target_functions=leaves,
                estimated_tokens=0,
                reason="Leaf functions (no dependencies) - verify first for quick wins"
            )
            phases.append(phase)
            verified.update(leaves)

        # Then topological sort for remaining
        phase_num = 1
        remaining = [f for f in code_structure.functions if f.name not in verified]

        while remaining:
            ready = []
            for func in remaining:
                deps = code_structure.dependency_graph.get(func.name, [])
                if all(d in verified for d in deps):
                    ready.append(func.name)

            if not ready:
                ready = [f.name for f in remaining][:1]

            phase = VerificationPhase(
                phase_number=phase_num,
                target_functions=ready,
                estimated_tokens=0,
                reason="Functions with verified dependencies"
            )
            phases.append(phase)

            verified.update(ready)
            remaining = [f for f in remaining if f.name not in verified]
            phase_num += 1

        return phases

    def _complexity_ascending_phases(self, code_structure: CodeStructure) -> List[VerificationPhase]:
        """Create phases with simple functions first."""
        sorted_funcs = sorted(
            code_structure.functions,
            key=lambda f: f.complexity_score
        )

        phase = VerificationPhase(
            phase_number=0,
            target_functions=[f.name for f in sorted_funcs],
            estimated_tokens=0,
            reason="All functions sorted by complexity (simple first)"
        )
        return [phase]

    def _module_scoped_phases(self, code_structure: CodeStructure) -> List[VerificationPhase]:
        """Create phases per module."""
        phases = []
        phase_num = 0

        for module_name, func_names in code_structure.modules.items():
            if func_names:
                phase = VerificationPhase(
                    phase_number=phase_num,
                    target_functions=func_names,
                    estimated_tokens=0,
                    reason=f"All functions in module '{module_name}'"
                )
                phases.append(phase)
                phase_num += 1

        return phases if phases else [VerificationPhase(
            phase_number=0,
            target_functions=[f.name for f in code_structure.functions],
            estimated_tokens=0,
            reason="All functions (no module info)"
        )]

    def _estimate_phase_cost(self, functions: List[str], code_structure: CodeStructure) -> int:
        """Estimate token cost for a phase."""
        total_cost = 0
        for func_name in functions:
            func = code_structure.function_by_name(func_name)
            if func:
                base_cost = self.TOKENS_PER_FUNCTION
                complexity_factor = self.COMPLEXITY_MULTIPLIER.get(
                    self._get_complexity_level(func.complexity_score),
                    1.0
                )
                line_factor = max(1.0, func.lines_of_code / 10)
                total_cost += int(base_cost * complexity_factor * line_factor)

        return total_cost

    def _assess_complexity(self, functions: List[str], code_structure: CodeStructure) -> str:
        """Assess overall complexity of a phase."""
        if not functions:
            return "simple"

        avg_complexity = sum(
            code_structure.function_by_name(f).complexity_score
            for f in functions
            if code_structure.function_by_name(f)
        ) / len(functions)

        return self._get_complexity_level(avg_complexity)

    def _get_complexity_level(self, complexity_score: float) -> str:
        """Get complexity level from score."""
        if complexity_score < 5:
            return "simple"
        elif complexity_score < 15:
            return "moderate"
        else:
            return "complex"

    def _merge_phases_to_budget(
        self, phases: List[VerificationPhase], budget: int
    ) -> List[VerificationPhase]:
        """Merge later phases to fit token budget."""
        merged = []
        current_phase = None
        current_cost = 0

        for phase in phases:
            if current_phase is None:
                current_phase = phase
                current_cost = phase.estimated_tokens
            elif current_cost + phase.estimated_tokens <= budget:
                # Merge with current
                current_phase.target_functions.extend(phase.target_functions)
                current_phase.estimated_tokens += phase.estimated_tokens
                current_cost += phase.estimated_tokens
            else:
                # Start new phase
                merged.append(current_phase)
                current_phase = phase
                current_cost = phase.estimated_tokens

        if current_phase:
            merged.append(current_phase)

        # Renumber phases
        for i, phase in enumerate(merged):
            phase.phase_number = i

        return merged
