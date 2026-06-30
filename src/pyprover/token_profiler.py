"""
PyProver v14.0 Phase 3A: Token Profiler
Real-time token cost tracking for verification operations.
Enables master-debugger to estimate costs before invoking pyprover.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import time
from enum import Enum

from .types_phase3 import (
    TokenProfile, TokenCostFactors, TokenProfileReport,
    OperationType, language_complexity_multiplier,
    estimate_async_overhead, estimate_ffi_overhead
)


class TokenProfiler:
    """
    Token cost estimation and tracking for PyProver operations.
    
    Usage:
        profiler = TokenProfiler()
        
        # Estimate cost before operation
        estimate = profiler.estimate_verify(
            contract_count=3,
            language="python",
            has_async=False,
            has_ffi=False
        )
        print(f"Estimated: {estimate.estimated_tokens} tokens")
        
        # Record actual cost after operation
        profiler.record_operation(
            operation=OperationType.VERIFY,
            estimated_tokens=estimate.estimated_tokens,
            actual_tokens=247,
            execution_time=0.8
        )
    """
    
    def __init__(self):
        """Initialize token profiler with baseline costs."""
        self.baseline_costs: Dict[OperationType, int] = {
            OperationType.VERIFY: 200,
            OperationType.SIMPLIFY: 150,
            OperationType.PROVE_INVARIANT: 250,
            OperationType.BATCH_VERIFY: 100,
            OperationType.ASYNC_VERIFY: 300,
            OperationType.FFI_VERIFY: 350,
        }
        
        self.scaling_factors: Dict[str, int] = {
            "per_contract": 20,
            "per_file": 50,
            "per_invariant": 30,
            "per_concurrent_var": 25,
            "per_ffi_param": 40,
        }
        
        self.language_multipliers = {
            "python": 1.0,
            "javascript": 1.2,
            "typescript": 1.3,
            "go": 1.5,
            "java": 1.8,
            "rust": 2.0,
            "c": 2.2,
            "cpp": 2.5,
            "nasm": 3.0,
            "fasm": 3.0,
            "wasm": 2.0,
            "csharp": 1.6,
        }
        
        self.report = TokenProfileReport()
        self.operation_history: List[TokenProfile] = []
    
    # ========================================================================
    # ESTIMATION METHODS
    # ========================================================================
    
    def estimate_verify(
        self,
        contract_count: int = 0,
        language: str = "python",
        has_async: bool = False,
        has_ffi: bool = False,
    ) -> TokenProfile:
        """
        Estimate token cost for verify() operation.
        
        Args:
            contract_count: Number of @requires/@ensures contracts
            language: Target language (python, rust, javascript, etc.)
            has_async: Whether code contains async functions
            has_ffi: Whether code contains FFI boundaries
            
        Returns:
            TokenProfile with estimated_tokens set
        """
        baseline = self.baseline_costs[OperationType.VERIFY]
        
        # Scale by contract count
        contract_cost = contract_count * self.scaling_factors["per_contract"]
        
        # Scale by language complexity
        lang_mult = self.language_multipliers.get(language.lower(), 1.5)
        lang_cost = int(baseline * (lang_mult - 1.0))
        
        # Add async overhead if present
        async_cost = 100 if has_async else 0
        
        # Add FFI overhead if present
        ffi_cost = 150 if has_ffi else 0
        
        total = baseline + contract_cost + lang_cost + async_cost + ffi_cost
        
        profile = TokenProfile(
            operation=OperationType.VERIFY,
            estimated_tokens=total,
            contract_count=contract_count,
            language=language,
            has_async=has_async,
            has_ffi=has_ffi,
        )
        
        return profile
    
    def estimate_simplify(
        self,
        clause_count: int = 1,
    ) -> TokenProfile:
        """
        Estimate token cost for simplify() operation.
        
        Args:
            clause_count: Number of clauses to simplify
            
        Returns:
            TokenProfile with estimated_tokens set
        """
        baseline = self.baseline_costs[OperationType.SIMPLIFY]
        clause_cost = clause_count * self.scaling_factors["per_contract"]
        total = baseline + clause_cost
        
        profile = TokenProfile(
            operation=OperationType.SIMPLIFY,
            estimated_tokens=total,
        )
        
        return profile
    
    def estimate_prove_invariant(
        self,
        invariant_count: int = 1,
        loop_complexity: int = 1,
    ) -> TokenProfile:
        """
        Estimate token cost for prove_invariant() operation.
        
        Args:
            invariant_count: Number of invariants to prove
            loop_complexity: 1-5 scale of loop complexity
            
        Returns:
            TokenProfile with estimated_tokens set
        """
        baseline = self.baseline_costs[OperationType.PROVE_INVARIANT]
        invariant_cost = invariant_count * self.scaling_factors["per_invariant"]
        complexity_cost = (loop_complexity - 1) * 50
        total = baseline + invariant_cost + complexity_cost
        
        profile = TokenProfile(
            operation=OperationType.PROVE_INVARIANT,
            estimated_tokens=total,
        )
        
        return profile
    
    def estimate_batch_verify(
        self,
        file_count: int = 1,
        parallel: bool = False,
    ) -> TokenProfile:
        """
        Estimate token cost for batch_verify() operation.
        
        Args:
            file_count: Number of files to verify
            parallel: Whether to use parallel processing
            
        Returns:
            TokenProfile with estimated_tokens set
        """
        baseline = self.baseline_costs[OperationType.BATCH_VERIFY]
        file_cost = file_count * self.scaling_factors["per_file"]
        
        # Parallel adds overhead but not linear scaling
        parallel_overhead = 50 if parallel else 0
        
        total = baseline + file_cost + parallel_overhead
        
        profile = TokenProfile(
            operation=OperationType.BATCH_VERIFY,
            estimated_tokens=total,
            file_count=file_count,
        )
        
        return profile
    
    def estimate_async_verify(
        self,
        async_pattern_count: int = 1,
        concurrent_variable_count: int = 0,
        language: str = "python",
    ) -> TokenProfile:
        """
        Estimate token cost for async_verify() operation (Phase 3B).
        
        Args:
            async_pattern_count: Number of async patterns detected
            concurrent_variable_count: Number of concurrent variables
            language: Target language
            
        Returns:
            TokenProfile with estimated_tokens set
        """
        baseline = self.baseline_costs[OperationType.ASYNC_VERIFY]
        pattern_cost = async_pattern_count * 50
        concurrent_cost = concurrent_variable_count * self.scaling_factors["per_concurrent_var"]
        
        lang_mult = self.language_multipliers.get(language.lower(), 1.5)
        lang_cost = int(50 * (lang_mult - 1.0))
        
        total = baseline + pattern_cost + concurrent_cost + lang_cost
        
        profile = TokenProfile(
            operation=OperationType.ASYNC_VERIFY,
            estimated_tokens=total,
            language=language,
            has_async=True,
        )
        
        return profile
    
    def estimate_ffi_verify(
        self,
        ffi_function_count: int = 1,
        parameter_count: int = 0,
        safety_checks: int = 0,
    ) -> TokenProfile:
        """
        Estimate token cost for ffi_verify() operation (Phase 3C).
        
        Args:
            ffi_function_count: Number of FFI functions
            parameter_count: Total parameters across FFI signatures
            safety_checks: Number of memory safety checks
            
        Returns:
            TokenProfile with estimated_tokens set
        """
        baseline = self.baseline_costs[OperationType.FFI_VERIFY]
        func_cost = ffi_function_count * 100
        param_cost = parameter_count * self.scaling_factors["per_ffi_param"]
        safety_cost = safety_checks * 30
        
        total = baseline + func_cost + param_cost + safety_cost
        
        profile = TokenProfile(
            operation=OperationType.FFI_VERIFY,
            estimated_tokens=total,
            has_ffi=True,
        )
        
        return profile
    
    # ========================================================================
    # RECORDING & TRACKING
    # ========================================================================
    
    def record_operation(
        self,
        operation: OperationType,
        estimated_tokens: int,
        actual_tokens: int,
        execution_time: float = 0.0,
        **kwargs: Any,
    ) -> TokenProfile:
        """
        Record completion of a verified operation with actual token cost.
        
        Args:
            operation: Type of operation
            estimated_tokens: Pre-estimated cost
            actual_tokens: Actual cost measured
            execution_time: Wall clock time in seconds
            **kwargs: Additional metadata (contract_count, language, etc.)
            
        Returns:
            Updated TokenProfile
        """
        profile = TokenProfile(
            operation=operation,
            estimated_tokens=estimated_tokens,
            actual_tokens=actual_tokens,
            execution_time_seconds=execution_time,
            **kwargs,
        )
        
        self.operation_history.append(profile)
        self.report.add_operation(profile)
        
        return profile
    
    def get_report(self) -> TokenProfileReport:
        """
        Get current token usage report.
        
        Returns:
            TokenProfileReport with aggregated statistics
        """
        return self.report
    
    def get_efficiency_stats(self) -> Dict[str, Any]:
        """
        Get statistics on estimate accuracy.
        
        Returns:
            Dict with average_efficiency, total_ops, outliers, etc.
        """
        if not self.operation_history:
            return {
                "total_operations": 0,
                "operations_with_actuals": 0,
                "average_efficiency": None,
                "outliers": [],
            }
        
        with_actuals = [op for op in self.operation_history if op.actual_tokens]
        
        if not with_actuals:
            return {
                "total_operations": len(self.operation_history),
                "operations_with_actuals": 0,
                "average_efficiency": None,
                "outliers": [],
            }
        
        efficiencies = [op.efficiency_ratio() for op in with_actuals]
        avg_eff = sum(efficiencies) / len(efficiencies)
        
        # Identify outliers (2x off from average)
        outliers = [
            {
                "operation": op.operation.value,
                "estimated": op.estimated_tokens,
                "actual": op.actual_tokens,
                "ratio": op.efficiency_ratio(),
            }
            for op in with_actuals
            if abs(op.efficiency_ratio() - avg_eff) > avg_eff * 1.0  # 2x deviation
        ]
        
        return {
            "total_operations": len(self.operation_history),
            "operations_with_actuals": len(with_actuals),
            "average_efficiency": avg_eff,
            "efficiency_std_dev": self._std_dev(efficiencies),
            "min_efficiency": min(efficiencies),
            "max_efficiency": max(efficiencies),
            "outliers": outliers,
        }
    
    def get_cost_history(
        self,
        operation_type: Optional[OperationType] = None,
        limit: int = 10,
    ) -> List[TokenProfile]:
        """
        Get recent operation history with optional filtering.
        
        Args:
            operation_type: Filter by operation type (or None for all)
            limit: Maximum number of operations to return
            
        Returns:
            List of TokenProfile objects (most recent first)
        """
        history = self.operation_history
        
        if operation_type:
            history = [op for op in history if op.operation == operation_type]
        
        return list(reversed(history[-limit:]))
    
    def estimate_total_cost(
        self,
        operations: List[Dict[str, Any]],
    ) -> int:
        """
        Estimate total token cost for a sequence of operations.
        
        Args:
            operations: List of dicts with operation specs
                Each dict should have 'type' and operation-specific params
                
        Returns:
            Total estimated tokens for entire sequence
        """
        total = 0
        
        for op_spec in operations:
            op_type = op_spec.get("type")
            
            if op_type == "verify":
                profile = self.estimate_verify(
                    contract_count=op_spec.get("contract_count", 1),
                    language=op_spec.get("language", "python"),
                    has_async=op_spec.get("has_async", False),
                    has_ffi=op_spec.get("has_ffi", False),
                )
            elif op_type == "simplify":
                profile = self.estimate_simplify(
                    clause_count=op_spec.get("clause_count", 1),
                )
            elif op_type == "prove_invariant":
                profile = self.estimate_prove_invariant(
                    invariant_count=op_spec.get("invariant_count", 1),
                    loop_complexity=op_spec.get("loop_complexity", 1),
                )
            elif op_type == "batch_verify":
                profile = self.estimate_batch_verify(
                    file_count=op_spec.get("file_count", 1),
                    parallel=op_spec.get("parallel", False),
                )
            elif op_type == "async_verify":
                profile = self.estimate_async_verify(
                    async_pattern_count=op_spec.get("async_pattern_count", 1),
                    concurrent_variable_count=op_spec.get("concurrent_variable_count", 0),
                    language=op_spec.get("language", "python"),
                )
            elif op_type == "ffi_verify":
                profile = self.estimate_ffi_verify(
                    ffi_function_count=op_spec.get("ffi_function_count", 1),
                    parameter_count=op_spec.get("parameter_count", 0),
                    safety_checks=op_spec.get("safety_checks", 0),
                )
            else:
                continue
            
            total += profile.estimated_tokens
        
        return total
    
    @staticmethod
    def _std_dev(values: List[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

# Global profiler instance for module-level access
_default_profiler = None


def get_profiler() -> TokenProfiler:
    """Get or create default profiler instance."""
    global _default_profiler
    if _default_profiler is None:
        _default_profiler = TokenProfiler()
    return _default_profiler


def estimate_verify(**kwargs) -> TokenProfile:
    """Convenience function to estimate verify cost."""
    return get_profiler().estimate_verify(**kwargs)


def estimate_async_verify(**kwargs) -> TokenProfile:
    """Convenience function to estimate async_verify cost."""
    return get_profiler().estimate_async_verify(**kwargs)


def estimate_ffi_verify(**kwargs) -> TokenProfile:
    """Convenience function to estimate ffi_verify cost."""
    return get_profiler().estimate_ffi_verify(**kwargs)
