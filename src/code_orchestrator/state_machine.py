"""State machine for managing verification state across prompts."""

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from .type_stubs import (
    CodeStructure,
    DecompositionPlan,
    FunctionResult,
    OperationError,
    OperationErrorType,
    VerificationPhaseStatus,
    VerificationState,
)


class VerificationStateMachine:
    """Manages verification state and transitions."""

    def __init__(self, codebase_hash: str = "", project_id: Optional[str] = None) -> None:
        """Initialize state machine.
        
        Args:
            codebase_hash: Hash of the codebase for change detection
            project_id: Project ID (auto-generated if not provided)
        """
        self.project_id = project_id or str(uuid4())
        self.codebase_hash = codebase_hash
        self.state = VerificationState(
            project_id=self.project_id,
            codebase_hash=codebase_hash
        )

    def initialize(
        self,
        code_structure: CodeStructure,
        decomposition_plan: DecompositionPlan,
        token_budget: int = 5000
    ) -> None:
        """Initialize state with code structure and plan.
        
        Args:
            code_structure: Extracted code structure
            decomposition_plan: Decomposition plan
            token_budget: Total token budget
        """
        self.state.code_structure = code_structure
        self.state.decomposition_plan = decomposition_plan
        self.state.functions_total = len(code_structure.functions)
        self.state.lines_total = code_structure.total_lines
        self.state.tokens_budget = token_budget
        self.state.pending_functions = [f.name for f in code_structure.functions]
        self.state.phase_status = VerificationPhaseStatus.PLANNED
        self.state.current_phase = 0
        self._log(f"Initialized: {self.state.functions_total} functions, {decomposition_plan.estimated_total_tokens} tokens estimated")

    def start_phase(self, phase_num: int) -> tuple[bool, Optional[str]]:
        """Start verification of a phase.
        
        Returns:
            Tuple of (success, error_message)
        """
        if not self.state.decomposition_plan or phase_num >= len(self.state.decomposition_plan.phases):
            return False, f"Invalid phase {phase_num}"

        self.state.current_phase = phase_num
        self.state.phase_status = VerificationPhaseStatus.VERIFYING
        self._log(f"Starting phase {phase_num}")
        return True, None

    def add_verified_function(self, name: str, result: FunctionResult) -> None:
        """Register a verified function.
        
        Args:
            name: Function name
            result: Verification result
        """
        self.state.add_verified_function(name, result)
        self.state.lines_verified += self._get_function_lines(name)
        self._log(f"Verified {name}: {result.status}")

    def mark_phase_complete(self) -> None:
        """Mark current phase as complete."""
        self.state.phase_status = VerificationPhaseStatus.COMPLETE
        self._log(f"Phase {self.state.current_phase} complete: {self.state.functions_verified}/{self.state.functions_total} functions verified")

    def pause_verification(self) -> None:
        """Pause verification (for checkpointing)."""
        self.state.phase_status = VerificationPhaseStatus.PAUSED
        self._log(f"Verification paused at phase {self.state.current_phase}")

    def update_tokens_spent(self, tokens: int) -> None:
        """Update token spending."""
        self.state.tokens_spent += tokens
        self.state.last_updated = datetime.now()

    def get_next_functions_to_verify(self) -> List[str]:
        """Get functions to verify in current phase."""
        if not self.state.decomposition_plan or self.state.current_phase >= len(self.state.decomposition_plan.phases):
            return []

        phase = self.state.decomposition_plan.phases[self.state.current_phase]
        return [f for f in phase.target_functions if f not in self.state.verified_functions]

    def get_coverage_percentage(self) -> float:
        """Get current coverage percentage."""
        return self.state.get_coverage_percentage()

    def get_blocked_functions(self) -> List[str]:
        """Get functions blocked by unverified dependencies."""
        blocked = []
        if not self.state.code_structure:
            return blocked

        for func_name in self.state.pending_functions:
            deps = self.state.code_structure.dependency_graph.get(func_name, [])
            if any(d not in self.state.verified_functions for d in deps):
                blocked.append(func_name)

        return blocked

    def export_state(self) -> VerificationState:
        """Export current state (for serialization)."""
        return self.state

    def import_state(self, state: VerificationState) -> None:
        """Import saved state."""
        self.state = state
        self.project_id = state.project_id
        self.codebase_hash = state.codebase_hash

    def detect_code_changes(self, new_hash: str) -> bool:
        """Detect if code has changed.
        
        Returns:
            True if code has changed since last state
        """
        if self.state.codebase_hash != new_hash:
            self._log(f"Code change detected: {self.state.codebase_hash} -> {new_hash}")
            return True
        return False

    def validate_state(self) -> Optional[OperationError]:
        """Validate state consistency.
        
        Returns:
            OperationError if invalid, None if valid
        """
        if not self.state.code_structure:
            return OperationError(
                error_type=OperationErrorType.STATE_ERROR,
                message="Code structure not initialized"
            )

        if not self.state.decomposition_plan:
            return OperationError(
                error_type=OperationErrorType.STATE_ERROR,
                message="Decomposition plan not initialized"
            )

        if self.state.functions_verified > self.state.functions_total:
            return OperationError(
                error_type=OperationErrorType.STATE_ERROR,
                message="Functions verified exceeds total"
            )

        return None

    def _get_function_lines(self, func_name: str) -> int:
        """Get lines of code for a function."""
        if self.state.code_structure:
            func = self.state.code_structure.function_by_name(func_name)
            if func:
                return func.lines_of_code
        return 0

    def _log(self, message: str) -> None:
        """Add to verification log."""
        timestamp = datetime.now().isoformat()
        self.state.verification_log.append(f"[{timestamp}] {message}")
