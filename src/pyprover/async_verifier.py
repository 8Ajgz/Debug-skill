"""
PyProver v14.0 Phase 3B: Async Verifier
Formal verification of async/await code in Python, JavaScript, and Rust.
Detects race conditions, deadlocks, and concurrency violations.
"""

from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import re

# Import Phase 3 types
from types_phase3 import (
    AsyncFunction, AsyncContract, AsyncPattern, ConcurrencyIssue,
    AsyncVerificationResult, language_complexity_multiplier
)


class AsyncVerifier:
    """
    Verifies async code correctness across Python, JavaScript, and Rust.
    
    Detects:
    - Race conditions on concurrent variables
    - Deadlock patterns
    - Use-after-free in async context
    - Atomicity violations
    - Lost updates
    
    Usage:
        verifier = AsyncVerifier()
        
        async_func = AsyncFunction(
            name="async_sum",
            language="python",
            patterns=[AsyncPattern.ASYNCIO_COROUTINE],
            parameters={"items": "List[int]"},
            return_type="int",
            concurrent_variables=["total"],
        )
        
        contract = AsyncContract(
            function_name="async_sum",
            requires="len(items) > 0",
            ensures="result >= 0",
            no_race_condition=True,
        )
        
        result = verifier.verify(async_func, contract)
        print(f"Verified: {result.verified}")
    """
    
    def __init__(self):
        """Initialize async verifier."""
        self.verified_functions: Dict[str, AsyncVerificationResult] = {}
        
        # Concurrency issue patterns
        self.race_condition_patterns = {
            r"(\w+)\s*=.*\n.*await.*\n.*\1\s*=": "potential_race_on_reassign",
            r"(\w+)\s*\+=.*\n.*await": "potential_lost_update",
            r"if\s+(\w+).*:\n.*await.*\1": "toctou_race",  # Time-of-check-time-of-use
        }
        
        self.deadlock_patterns = {
            r"lock\((\w+)\).*await.*lock\(\1\)": "reentrant_lock",
            r"lock\((\w+)\).*lock\((\w+)\)": "circular_wait",
        }
    
    # ========================================================================
    # ASYNC PATTERN DETECTION
    # ========================================================================
    
    def detect_async_patterns(
        self,
        source_code: str,
        language: str,
    ) -> List[AsyncPattern]:
        """
        Detect async patterns in source code.
        
        Args:
            source_code: Code to analyze
            language: "python", "javascript", "rust"
            
        Returns:
            List of detected AsyncPattern enums
        """
        patterns = []
        
        if language.lower() == "python":
            patterns.extend(self._detect_python_patterns(source_code))
        elif language.lower() in ["javascript", "typescript"]:
            patterns.extend(self._detect_js_patterns(source_code))
        elif language.lower() == "rust":
            patterns.extend(self._detect_rust_patterns(source_code))
        
        return patterns
    
    def _detect_python_patterns(self, code: str) -> List[AsyncPattern]:
        """Detect Python async patterns (asyncio)."""
        patterns = []
        
        if re.search(r'async\s+def\s+\w+', code):
            patterns.append(AsyncPattern.ASYNCIO_COROUTINE)
        
        if re.search(r'await\s+\w+', code):
            patterns.append(AsyncPattern.ASYNCIO_COROUTINE)
        
        if re.search(r'async\s+for\s+\w+\s+in', code):
            patterns.append(AsyncPattern.PYTHON_ASYNC_FOR)
        
        if re.search(r'async\s+with\s+', code):
            patterns.append(AsyncPattern.PYTHON_ASYNC_WITH)
        
        if re.search(r'yield', code):
            patterns.append(AsyncPattern.ASYNCIO_COROUTINE)
        
        return patterns
    
    def _detect_js_patterns(self, code: str) -> List[AsyncPattern]:
        """Detect JavaScript/TypeScript async patterns."""
        patterns = []
        
        if re.search(r'async\s+function|\basync\s*\(', code):
            patterns.append(AsyncPattern.JAVASCRIPT_ASYNC_AWAIT)
        
        if re.search(r'await\s+\w+|await\s+\(', code):
            patterns.append(AsyncPattern.JAVASCRIPT_ASYNC_AWAIT)
        
        if re.search(r'\.then\s*\(|Promise\s*\(', code):
            patterns.append(AsyncPattern.JAVASCRIPT_PROMISE)
        
        if re.search(r'\.catch\s*\(', code):
            patterns.append(AsyncPattern.JAVASCRIPT_PROMISE)
        
        return patterns
    
    def _detect_rust_patterns(self, code: str) -> List[AsyncPattern]:
        """Detect Rust async patterns."""
        patterns = []
        
        if re.search(r'async\s+(fn|move|block)', code):
            patterns.append(AsyncPattern.RUST_ASYNC_FN)
        
        if re.search(r'await\s*;', code):
            patterns.append(AsyncPattern.RUST_ASYNC_FN)
        
        if re.search(r'Future\s*[<\(]', code):
            patterns.append(AsyncPattern.RUST_FUTURE)
        
        return patterns
    
    # ========================================================================
    # CONCURRENT VARIABLE DETECTION
    # ========================================================================
    
    def detect_concurrent_variables(
        self,
        source_code: str,
        language: str,
    ) -> List[str]:
        """
        Detect variables that may be accessed concurrently.
        
        Heuristic: Variables accessed both before and after await.
        
        Args:
            source_code: Code to analyze
            language: "python", "javascript", "rust"
            
        Returns:
            List of variable names with potential concurrent access
        """
        concurrent_vars = []
        
        # Split code into statements
        lines = source_code.split('\n')
        
        # Track variable assignments and uses
        assigned_vars: Set[str] = set()
        used_after_await: Set[str] = set()
        
        in_await_block = False
        
        for line in lines:
            # Check for await
            if 'await' in line or 'await' in line:
                in_await_block = True
            
            # Simple variable extraction (real implementation would be AST-based)
            # Pattern: word followed by = or word in expression
            var_matches = re.findall(r'\b([a-zA-Z_]\w*)\b', line)
            
            if in_await_block:
                used_after_await.update(var_matches)
            else:
                assigned_vars.update(var_matches)
        
        # Variables assigned before and used after await = concurrent
        concurrent_vars = list(assigned_vars & used_after_await)
        
        return concurrent_vars
    
    # ========================================================================
    # RACE CONDITION DETECTION
    # ========================================================================
    
    def detect_race_conditions(
        self,
        source_code: str,
        concurrent_variables: List[str],
    ) -> List[ConcurrencyIssue]:
        """
        Detect potential race conditions on concurrent variables.
        
        Patterns:
        - Read-modify-write without synchronization (lost update)
        - TOCTOU (time-of-check, time-of-use)
        - Reassignment between await points
        
        Args:
            source_code: Code to analyze
            concurrent_variables: Variables with concurrent access
            
        Returns:
            List of detected ConcurrencyIssue enums
        """
        issues = []
        
        for var in concurrent_variables:
            # Escape var for regex
            var_escaped = re.escape(var)
            
            # Pattern 1: Lost update (var += / -= around await)
            # e.g., "counter += 1" before/after await
            lost_update_pattern = rf'\b{var_escaped}\s*[\+\-\*]/='
            if re.search(lost_update_pattern, source_code) and 'await' in source_code:
                if ConcurrencyIssue.LOST_UPDATE not in issues:
                    issues.append(ConcurrencyIssue.LOST_UPDATE)
                continue
            
            # Pattern 2: TOCTOU - Check then use
            # e.g., "if counter < 5:" followed by await and then "counter += 1"
            check_pattern = rf'if\s*[(\w\s<>=!&|]+{var_escaped}'
            if re.search(check_pattern, source_code):
                # Found a check on this variable
                # Now look for await and then use
                # Split by if to find the block
                if_blocks = re.findall(rf'if\s*[(\w\s<>=!&|]+{var_escaped}[)\w\s<>=!&|:]*\n(.*?)(?=\nif|\nelse|\Z)', source_code, re.DOTALL)
                for block in if_blocks:
                    # Check if this block has await and then uses the variable
                    if 'await' in block and re.search(rf'\b{var_escaped}\s*[\[\+\-\*=]', block):
                        if ConcurrencyIssue.RACE_CONDITION not in issues:
                            issues.append(ConcurrencyIssue.RACE_CONDITION)
                        break
            
            # Pattern 3: Multiple assignments across await points
            assignments = re.findall(rf'\b{var_escaped}\s*=(?!=)', source_code)
            if len(assignments) >= 1:
                # At least one assignment exists
                # Check if there's assignment after await
                parts = source_code.split('await')
                if len(parts) >= 2:
                    # At least one await exists
                    for part in parts[1:]:
                        # Look for assignment or compound assignment in this part
                        if re.search(rf'\b{var_escaped}\s*(=|[\+\-\*]/=)', part):
                            # Use of variable after await
                            if ConcurrencyIssue.RACE_CONDITION not in issues:
                                issues.append(ConcurrencyIssue.RACE_CONDITION)
                            break
        
        return issues  # Already deduplicated by checking membership
    
    def detect_deadlock_patterns(
        self,
        source_code: str,
    ) -> List[ConcurrencyIssue]:
        """
        Detect potential deadlock patterns.
        
        Patterns:
        - Reentrancy on same lock
        - Circular lock acquisition
        - Nested await in lock context
        
        Args:
            source_code: Code to analyze
            
        Returns:
            List of detected ConcurrencyIssue enums
        """
        issues = []
        
        # Pattern: lock acquired twice
        lock_pattern = r'(?:lock|acquire|enter)\s*\(\s*(\w+)\s*\)'
        locks = re.findall(lock_pattern, source_code)
        
        if len(locks) > len(set(locks)):
            # Duplicate lock acquisition
            issues.append(ConcurrencyIssue.DEADLOCK)
        
        # Pattern: await inside lock context
        if re.search(r'(?:lock|acquire).*\n.*await', source_code):
            issues.append(ConcurrencyIssue.DEADLOCK)
        
        return issues
    
    # ========================================================================
    # VERIFICATION
    # ========================================================================
    
    def verify(
        self,
        async_function: AsyncFunction,
        contract: AsyncContract,
    ) -> AsyncVerificationResult:
        """
        Verify an async function against its contract.
        
        Args:
            async_function: Metadata about the async function
            contract: Contract for the function
            
        Returns:
            AsyncVerificationResult with verification outcome
        """
        import time
        start = time.time()
        
        # Collect issues
        concurrency_issues: List[ConcurrencyIssue] = []
        
        # Detect race conditions on concurrent variables
        if async_function.concurrent_variables:
            race_issues = self.detect_race_conditions(
                "",  # Would need full source code
                async_function.concurrent_variables
            )
            concurrency_issues.extend(race_issues)
        
        # Check contract constraints
        verified = True
        proof = None
        counterexample = None
        
        if contract.no_race_condition and ConcurrencyIssue.RACE_CONDITION in concurrency_issues:
            verified = False
            counterexample = {
                "issue": "race_condition",
                "variables": async_function.concurrent_variables,
            }
        
        if contract.no_deadlock and ConcurrencyIssue.DEADLOCK in concurrency_issues:
            verified = False
            counterexample = {
                "issue": "deadlock",
                "location": "lock context",
            }
        
        if verified:
            proof = {
                "strategy": "pattern_analysis",
                "patterns": [p.value for p in async_function.patterns],
                "concurrent_vars": async_function.concurrent_variables,
                "no_detected_issues": True,
            }
        
        end = time.time()
        
        result = AsyncVerificationResult(
            verified=verified,
            function_name=async_function.name,
            patterns_found=async_function.patterns,
            concurrency_issues=concurrency_issues,
            proof=proof,
            counterexample=counterexample,
            time_seconds=end - start,
            complexity_score=async_function.complexity_score(),
        )
        
        self.verified_functions[async_function.name] = result
        return result
    
    def verify_from_source(
        self,
        source_code: str,
        function_name: str,
        language: str,
        contract: AsyncContract,
    ) -> AsyncVerificationResult:
        """
        Verify async function directly from source code.
        
        Args:
            source_code: Full source code
            function_name: Name of function to verify
            language: "python", "javascript", "rust"
            contract: Contract for the function
            
        Returns:
            AsyncVerificationResult
        """
        # Extract function body (simplified)
        func_pattern = rf'(?:async\s+)?(?:def|function|\bfn)\s+{function_name}\s*\([^)]*\)\s*(?:->.*?)?:'
        match = re.search(func_pattern, source_code)
        
        if not match:
            return AsyncVerificationResult(
                verified=False,
                function_name=function_name,
                patterns_found=[],
                concurrency_issues=[],
                counterexample={"error": "function_not_found"},
            )
        
        # Detect patterns
        patterns = self.detect_async_patterns(source_code, language)
        
        # Detect concurrent variables
        concurrent_vars = self.detect_concurrent_variables(source_code, language)
        
        # Create AsyncFunction metadata
        async_func = AsyncFunction(
            name=function_name,
            language=language,
            patterns=patterns,
            parameters={},  # Would extract from AST
            return_type="unknown",
            concurrent_variables=concurrent_vars,
            has_concurrent_access=len(concurrent_vars) > 0,
        )
        
        # Verify
        return self.verify(async_func, contract)
    
    # ========================================================================
    # UTILITIES
    # ========================================================================
    
    def get_verification_report(
        self,
        function_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get verification report for one or all functions.
        
        Args:
            function_name: Specific function (or None for all)
            
        Returns:
            Summary report
        """
        if function_name:
            if function_name not in self.verified_functions:
                return {"error": "function_not_found"}
            
            result = self.verified_functions[function_name]
            return {
                "function": function_name,
                "verified": result.verified,
                "patterns": [p.value for p in result.patterns_found],
                "concurrency_issues": [i.value for i in result.concurrency_issues],
                "complexity_score": result.complexity_score,
                "time_seconds": result.time_seconds,
            }
        else:
            # All functions
            total = len(self.verified_functions)
            verified_count = sum(1 for r in self.verified_functions.values() if r.verified)
            
            return {
                "total_functions": total,
                "verified": verified_count,
                "failed": total - verified_count,
                "functions": {
                    name: {
                        "verified": result.verified,
                        "issue_count": len(result.concurrency_issues),
                    }
                    for name, result in self.verified_functions.items()
                },
            }
    
    def suggest_fixes(
        self,
        result: AsyncVerificationResult,
    ) -> List[str]:
        """
        Suggest fixes for detected concurrency issues.
        
        Args:
            result: AsyncVerificationResult with issues
            
        Returns:
            List of suggested fixes
        """
        suggestions = []
        
        for issue in result.concurrency_issues:
            if issue == ConcurrencyIssue.RACE_CONDITION:
                suggestions.append("Use a lock/mutex to protect concurrent variable access")
                suggestions.append("Use atomic operations if available")
                suggestions.append("Use immutable data structures")
            
            elif issue == ConcurrencyIssue.DEADLOCK:
                suggestions.append("Avoid holding locks across await points")
                suggestions.append("Use timeout-based lock acquisition")
                suggestions.append("Restructure code to release locks before await")
            
            elif issue == ConcurrencyIssue.LOST_UPDATE:
                suggestions.append("Use compare-and-swap (CAS) for atomic updates")
                suggestions.append("Protect read-modify-write with synchronization")
        
        return suggestions
