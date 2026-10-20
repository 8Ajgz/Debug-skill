"""Main orchestrator coordinating systematic code verification."""

import hashlib
from pathlib import Path
from typing import Optional, Tuple

from .code_analyzer import CodeAnalyzer
from .coverage import CoverageTracker
from .decomposition import DecompositionPlanner
from .handoff import VerificationStateIO
from .reporting import ReportGenerator
from .state_machine import VerificationStateMachine
from .tool_recommender import ToolRecommender
from .types import (
    CoverageReport,
    CodeStructure,
    DecompositionPlan,
    OperationError,
    ToolRecommendation,
    VerificationState,
)
from .types import FunctionResult
from .github_analyzer import GitHubProjectAnalyzer
from .multi_file_analyzer import MultiFileAnalyzer
from .test_target_extractor import TestTargetExtractor
from .project_structure import GitHubProject, ProjectStructure


class CodeOrchestrator:
    """Main orchestrator for systematic code verification."""

    def __init__(self) -> None:
        """Initialize the orchestrator."""
        self.analyzer = CodeAnalyzer()
        self.planner = DecompositionPlanner()
        self.state_machine: Optional[VerificationStateMachine] = None
        self.coverage_tracker = CoverageTracker()
        self.tool_recommender = ToolRecommender()
        self.report_generator = ReportGenerator()
        # GitHub integration
        self.github_analyzer = GitHubProjectAnalyzer()
        self.multi_file_analyzer = MultiFileAnalyzer()
        self.test_target_extractor = TestTargetExtractor()

    def analyze_codebase(
        self,
        source_code: str,
        language: str = "python",
        strategy: str = "topological_sort",
        token_budget: int = 5000
    ) -> Tuple[Optional[VerificationState], Optional[OperationError]]:
        """Analyze codebase and create decomposition plan.
        
        Args:
            source_code: Source code to analyze
            language: Programming language
            strategy: Decomposition strategy
            token_budget: Total token budget
            
        Returns:
            Tuple of (VerificationState, None) on success or (None, OperationError) on failure
        """
        # Extract code structure
        structure, error = self.analyzer.extract_from_source(source_code, language)
        if error:
            return None, error

        # Create decomposition plan
        plan = self.planner.plan(structure, strategy=strategy, token_budget=token_budget)

        # Initialize state machine
        codebase_hash = self._compute_hash(source_code)
        self.state_machine = VerificationStateMachine(codebase_hash=codebase_hash)
        self.state_machine.initialize(structure, plan, token_budget=token_budget)

        return self.state_machine.export_state(), None

    def analyze_github_project(
        self,
        github_url: str,
        target_count: int = 10,
        token_budget: int = 8000
    ) -> Tuple[Optional[VerificationState], Optional[OperationError]]:
        """Analyze a GitHub project and prepare for verification.
        
        Args:
            github_url: GitHub repository URL
            target_count: Number of functions to target for verification
            token_budget: Total token budget for verification
            
        Returns:
            Tuple of (VerificationState, None) on success or (None, OperationError) on failure
        """
        try:
            # Clone and analyze project
            project = self.github_analyzer.analyze_github_project(github_url)
            
            # Analyze file structure
            files = self.multi_file_analyzer.analyze_project_structure(project.local_path)
            
            # Extract test targets
            targets = self.test_target_extractor.extract_test_targets(
                project.local_path, project, target_count
            )
            
            if not targets:
                error = OperationError(
                    type="NO_VERIFIABLE_TARGETS",
                    message=f"No suitable functions found in {project.repo_name}",
                    context={"repo": github_url}
                )
                return None, error
            
            # Extract Python code from project (combine all functions)
            source_code = self._extract_source_from_project(project.local_path)
            if not source_code:
                error = OperationError(
                    type="NO_SOURCE_CODE",
                    message=f"No Python source code found in {project.repo_name}",
                    context={"repo": github_url}
                )
                return None, error
            
            # Create code structure
            structure, error = self.analyzer.extract_from_source(source_code, "python")
            if error:
                return None, error
            
            # Create decomposition plan
            plan = self.planner.plan(structure, strategy="topological_sort", token_budget=token_budget)
            
            # Initialize state machine
            codebase_hash = self._compute_hash(source_code)
            self.state_machine = VerificationStateMachine(codebase_hash=codebase_hash)
            self.state_machine.initialize(structure, plan, token_budget=token_budget)
            
            state = self.state_machine.export_state()
            # Add GitHub metadata
            state.metadata = {
                "source": "github",
                "github_url": github_url,
                "repo_name": project.repo_name,
                "functions_in_project": project.functions_found,
                "target_count": target_count,
            }
            
            return state, None
            
        except Exception as e:
            error = OperationError(
                type="GITHUB_ANALYSIS_ERROR",
                message=str(e),
                context={"github_url": github_url}
            )
            return None, error

    def verify_github_project(
        self,
        github_url: str,
        phases: Optional[list] = None,
        token_budget: int = 8000
    ) -> Tuple[Optional[VerificationState], Optional[OperationError]]:
        """Complete verification workflow for a GitHub project.
        
        Args:
            github_url: GitHub repository URL
            phases: Phases to run (default: [1, 2])
            token_budget: Total token budget
            
        Returns:
            Tuple of (VerificationState, None) on success or (None, OperationError) on failure
        """
        if phases is None:
            phases = [1, 2]
        
        # Analyze project
        state, error = self.analyze_github_project(github_url, token_budget=token_budget)
        if error:
            return None, error
        
        # Run each phase
        for phase in phases:
            result = self.run_phase(state, phase)
            if result.get("error"):
                error = OperationError(
                    type="PHASE_ERROR",
                    message=f"Error in phase {phase}: {result.get('error')}",
                    context={"phase": phase}
                )
                return None, error
            state = result.get("next_state", state)
        
        return state, None

    def _extract_source_from_project(self, repo_path: Path) -> str:
        """Extract and concatenate all Python source code from project."""
        sources = []
        for py_file in sorted(repo_path.rglob("*.py")):
            if self._should_skip_file(py_file):
                continue
            try:
                with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    rel_path = py_file.relative_to(repo_path)
                    sources.append(f"# File: {rel_path}\n{content}\n")
            except Exception:
                pass
        
        return "\n".join(sources)

    @staticmethod
    def _should_skip_file(file_path: Path) -> bool:
        """Check if file should be skipped."""
        skip_patterns = [
            "__pycache__",
            ".git",
            "venv",
            "env",
            ".egg",
            "build",
            "dist",
            "/test",
            "/tests",
        ]
        
        path_str = str(file_path)
        return any(pattern in path_str for pattern in skip_patterns)

    def run_phase(
        self,
        state: VerificationState,
        phase: int,
        tools: Optional[list] = None
    ) -> dict:
        """Run verification on a specific phase.
        
        Args:
            state: Current verification state
            phase: Phase number to run
            tools: List of tools to use (optional)
            
        Returns:
            Dict with phase results and updated state
        """
        # Import state
        if not self.state_machine:
            codebase_hash = state.codebase_hash
            self.state_machine = VerificationStateMachine(codebase_hash=codebase_hash)
            self.state_machine.import_state(state)

        # Start phase
        success, error = self.state_machine.start_phase(phase)
        if not success:
            return {"error": error, "success": False}

        # Get functions to verify
        functions_to_verify = self.state_machine.get_next_functions_to_verify()

        # Recommend tools if not specified
        if tools is None:
            rec = self.tool_recommender.recommend_next_tool(state)
            tools = [rec.recommended_tool]

        # Record tools to run
        for tool in tools:
            if tool not in state.tools_run:
                state.tools_run[tool] = []
            state.tools_run[tool].extend(functions_to_verify)

        # Mark phase complete (in real scenario, tools would update state)
        self.state_machine.mark_phase_complete()

        return {
            "success": True,
            "phase": phase,
            "functions_verified": len(functions_to_verify),
            "recommended_tools": tools,
            "next_state": self.state_machine.export_state()
        }

    def get_coverage_report(self, state: VerificationState) -> CoverageReport:
        """Get unified coverage report.
        
        Args:
            state: Verification state
            
        Returns:
            CoverageReport with metrics
        """
        return self.coverage_tracker.compute(state)

    def recommend_next_tool(self, state: VerificationState) -> ToolRecommendation:
        """Recommend next tool.
        
        Args:
            state: Verification state
            
        Returns:
            ToolRecommendation
        """
        return self.tool_recommender.recommend_next_tool(state)

    def get_state_checkpoint(self, state: VerificationState) -> str:
        """Serialize state to JSON checkpoint.
        
        Args:
            state: Verification state
            
        Returns:
            JSON checkpoint string
        """
        return VerificationStateIO.serialize(state)

    def load_checkpoint(self, checkpoint_json: str) -> Tuple[Optional[VerificationState], Optional[OperationError]]:
        """Deserialize state from checkpoint.
        
        Args:
            checkpoint_json: JSON checkpoint string
            
        Returns:
            Tuple of (VerificationState, None) on success or (None, OperationError) on failure
        """
        return VerificationStateIO.deserialize(checkpoint_json)

    def get_human_readable_report(self, state: VerificationState) -> str:
        """Get human-readable coverage report.
        
        Args:
            state: Verification state
            
        Returns:
            Formatted report string
        """
        report = self.coverage_tracker.compute(state)
        return self.report_generator.generate_coverage_report(report)

    def get_next_steps(self, state: VerificationState) -> str:
        """Get recommendation for next steps.
        
        Args:
            state: Verification state
            
        Returns:
            Next steps recommendation
        """
        return self.report_generator.generate_next_steps_recommendation(state)

    def get_summary(self, state: VerificationState) -> str:
        """Get brief verification summary.
        
        Args:
            state: Verification state
            
        Returns:
            Summary string
        """
        return self.report_generator.generate_summary(state)

    @staticmethod
    def _compute_hash(source_code: str) -> str:
        """Compute SHA256 hash of source code.
        
        Args:
            source_code: Source code
            
        Returns:
            SHA256 hash string
        """
        return hashlib.sha256(source_code.encode()).hexdigest()


# Convenience functions for direct use
def analyze_codebase(
    source_code: str,
    language: str = "python",
    strategy: str = "topological_sort",
    token_budget: int = 5000
) -> Tuple[Optional[VerificationState], Optional[OperationError]]:
    """Convenience function to analyze codebase."""
    orchestrator = CodeOrchestrator()
    return orchestrator.analyze_codebase(source_code, language, strategy, token_budget)


def run_phase(
    state: VerificationState,
    phase: int,
    tools: Optional[list] = None
) -> dict:
    """Convenience function to run a verification phase."""
    orchestrator = CodeOrchestrator()
    return orchestrator.run_phase(state, phase, tools)


def get_coverage_report(state: VerificationState) -> CoverageReport:
    """Convenience function to get coverage report."""
    orchestrator = CodeOrchestrator()
    return orchestrator.get_coverage_report(state)
