"""Stateful handoff protocol for serializing verification state across prompts."""

import json
from dataclasses import asdict
from datetime import datetime
from typing import Optional, Tuple

from .types import (
    CodeStructure,
    DecompositionPlan,
    Function,
    OperationError,
    OperationErrorType,
    VerificationPhase,
    VerificationState,
)
from .types import FunctionResult, VerificationPhaseStatus


class VerificationStateIO:
    """Handles serialization and deserialization of verification state."""

    @staticmethod
    def serialize(state: VerificationState) -> str:
        """Convert VerificationState to JSON checkpoint.
        
        Args:
            state: VerificationState to serialize
            
        Returns:
            JSON string checkpoint
        """
        checkpoint = {
            "metadata": {
                "project_id": state.project_id,
                "codebase_hash": state.codebase_hash,
                "created_at": state.created_at.isoformat(),
                "last_updated": state.last_updated.isoformat(),
                "prompts_used": state.prompts_used,
                "version": "1.0"
            },
            "progress": {
                "current_phase": state.current_phase,
                "phase_status": state.phase_status.value,
                "functions_verified": state.functions_verified,
                "functions_total": state.functions_total,
                "lines_verified": state.lines_verified,
                "lines_total": state.lines_total,
                "tokens_spent": state.tokens_spent,
                "tokens_budget": state.tokens_budget
            },
            "results": {
                "verified_functions": {
                    name: VerificationStateIO._serialize_function_result(result)
                    for name, result in state.verified_functions.items()
                },
                "pending_functions": state.pending_functions,
                "failed_functions": state.failed_functions,
                "blocked_functions": state.blocked_functions
            },
            "tools_run": state.tools_run,
            "structure": {
                "code_structure": VerificationStateIO._serialize_code_structure(state.code_structure),
                "decomposition_plan": VerificationStateIO._serialize_decomposition_plan(state.decomposition_plan),
            },
            "next_steps": VerificationStateIO._generate_next_steps(state),
            "log": state.verification_log[-5:] if state.verification_log else []  # Last 5 entries
        }

        return json.dumps(checkpoint, indent=2)

    @staticmethod
    def deserialize(checkpoint_json: str) -> Tuple[Optional[VerificationState], Optional[OperationError]]:
        """Load VerificationState from JSON checkpoint.
        
        Args:
            checkpoint_json: JSON string checkpoint
            
        Returns:
            Tuple of (VerificationState, None) on success or (None, OperationError) on failure
        """
        try:
            data = json.loads(checkpoint_json)
        except json.JSONDecodeError as e:
            return None, OperationError(
                error_type=OperationErrorType.CHECKPOINT_ERROR,
                message=f"Invalid JSON: {str(e)}"
            )

        try:
            # Reconstruct state
            state = VerificationState(
                project_id=data["metadata"]["project_id"],
                codebase_hash=data["metadata"]["codebase_hash"],
                functions_verified=data["progress"]["functions_verified"],
                functions_total=data["progress"]["functions_total"],
                lines_verified=data["progress"]["lines_verified"],
                lines_total=data["progress"]["lines_total"],
                tokens_spent=data["progress"]["tokens_spent"],
                tokens_budget=data["progress"]["tokens_budget"],
                current_phase=data["progress"]["current_phase"],
                phase_status=VerificationPhaseStatus(data["progress"]["phase_status"]),
                prompts_used=data["metadata"]["prompts_used"],
                created_at=datetime.fromisoformat(data["metadata"]["created_at"]),
                last_updated=datetime.fromisoformat(data["metadata"]["last_updated"]),
                pending_functions=data["results"]["pending_functions"],
                failed_functions=data["results"]["failed_functions"],
                blocked_functions=data["results"]["blocked_functions"],
                tools_run=data["tools_run"]
            )

            # Reconstruct verified functions
            for name, result_data in data["results"]["verified_functions"].items():
                result = VerificationStateIO._deserialize_function_result(result_data)
                state.verified_functions[name] = result

            # Restore verification log
            state.verification_log = data.get("log", [])

            # Restore code structure and plan (absent in checkpoints written before this field)
            structure = data.get("structure", {})
            state.code_structure = VerificationStateIO._deserialize_code_structure(
                structure.get("code_structure"))
            state.decomposition_plan = VerificationStateIO._deserialize_decomposition_plan(
                structure.get("decomposition_plan"))

            return state, None

        except (KeyError, ValueError) as e:
            return None, OperationError(
                error_type=OperationErrorType.CHECKPOINT_ERROR,
                message=f"Corrupted checkpoint: {str(e)}"
            )

    @staticmethod
    def validate_checkpoint(checkpoint: dict) -> Tuple[bool, str]:
        """Verify checkpoint is well-formed.
        
        Args:
            checkpoint: Checkpoint dictionary
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_keys = ["metadata", "progress", "results", "tools_run"]
        for key in required_keys:
            if key not in checkpoint:
                return False, f"Missing required key: {key}"

        # Validate metadata
        meta_keys = ["project_id", "codebase_hash", "created_at", "version"]
        for key in meta_keys:
            if key not in checkpoint["metadata"]:
                return False, f"Missing metadata key: {key}"

        # Validate progress
        progress_keys = ["current_phase", "phase_status", "functions_verified", "functions_total"]
        for key in progress_keys:
            if key not in checkpoint["progress"]:
                return False, f"Missing progress key: {key}"

        # Validate results
        if not all(k in checkpoint["results"] for k in ["verified_functions", "pending_functions"]):
            return False, "Missing results keys"

        return True, ""

    @staticmethod
    def _serialize_function_result(result: FunctionResult) -> dict:
        """Serialize a FunctionResult to dict."""
        return {
            "function_name": result.function_name,
            "verified": result.verified,
            "status": result.status,
            "failure_reason": result.failure_reason,
            "dependencies_verified": result.dependencies_verified,
            "tools_run": result.tools_run,
            "timestamp": result.timestamp.isoformat()
        }

    @staticmethod
    def _deserialize_function_result(data: dict) -> FunctionResult:
        """Deserialize a FunctionResult from dict."""
        return FunctionResult(
            function_name=data["function_name"],
            verified=data["verified"],
            status=data.get("status", "pending"),
            failure_reason=data.get("failure_reason"),
            dependencies_verified=data.get("dependencies_verified", False),
            tools_run=data.get("tools_run", {}),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat()))
        )

    @staticmethod
    def _serialize_code_structure(structure: Optional[CodeStructure]) -> Optional[dict]:
        if structure is None:
            return None
        return {
            "functions": [
                {
                    "name": f.name,
                    "module": f.module,
                    "lines_of_code": f.lines_of_code,
                    "complexity_score": f.complexity_score,
                    "callees": f.callees,
                    "callers": f.callers,
                    "is_testable": f.is_testable,
                    "is_verifiable": f.is_verifiable,
                    "docstring": f.docstring,
                }
                for f in structure.functions
            ],
            "call_graph": structure.call_graph,
            "dependency_graph": structure.dependency_graph,
            "modules": structure.modules,
            "total_lines": structure.total_lines,
            "analyzable_percentage": structure.analyzable_percentage,
            "language": structure.language,
        }

    @staticmethod
    def _deserialize_code_structure(data: Optional[dict]) -> Optional[CodeStructure]:
        if not data:
            return None
        return CodeStructure(
            functions=[Function(**f) for f in data["functions"]],
            call_graph=data["call_graph"],
            dependency_graph=data["dependency_graph"],
            modules=data["modules"],
            total_lines=data["total_lines"],
            analyzable_percentage=data["analyzable_percentage"],
            language=data.get("language", "python"),
        )

    @staticmethod
    def _serialize_decomposition_plan(plan: Optional[DecompositionPlan]) -> Optional[dict]:
        if plan is None:
            return None
        return {
            "phases": [asdict(p) for p in plan.phases],
            "total_functions": plan.total_functions,
            "total_lines": plan.total_lines,
            "estimated_total_tokens": plan.estimated_total_tokens,
            "strategy": plan.strategy,
            "coverage_target": plan.coverage_target,
        }

    @staticmethod
    def _deserialize_decomposition_plan(data: Optional[dict]) -> Optional[DecompositionPlan]:
        if not data:
            return None
        return DecompositionPlan(
            phases=[VerificationPhase(**p) for p in data["phases"]],
            total_functions=data["total_functions"],
            total_lines=data["total_lines"],
            estimated_total_tokens=data["estimated_total_tokens"],
            strategy=data["strategy"],
            coverage_target=data.get("coverage_target", "100% of analyzable code"),
        )

    @staticmethod
    def _generate_next_steps(state: VerificationState) -> list:
        """Generate recommended next steps."""
        steps = []

        if state.functions_verified < state.functions_total:
            remaining = state.functions_total - state.functions_verified
            steps.append(f"Verify remaining {remaining} functions")

        if state.blocked_functions:
            steps.append(f"Resolve {len(state.blocked_functions)} blocked functions")

        if state.failed_functions:
            steps.append(f"Investigate {len(state.failed_functions)} failures")

        if state.tokens_spent >= state.tokens_budget:
            steps.append("Increase token budget to continue")

        if not steps:
            steps.append("Verification complete!")

        return steps
