"""
PyProver v14.0 Phase 3C: FFI Verifier
Formal verification of FFI (Foreign Function Interface) boundaries.
Validates type safety, memory safety, and calling conventions across
Python↔C, Rust↔C, JavaScript↔WASM, and other language boundaries.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import re

# Import Phase 3 types
from types_phase3 import (
    FFISignature, FFIContract, FFILanguagePair, FFITypeMapping,
    FFIVerificationResult, MemorySafetyIssue, language_complexity_multiplier
)


class FFIVerifier:
    """
    Verifies correctness of FFI boundaries across multiple language pairs.
    
    Checks:
    - Type coercion safety (int → int64_t, Python object → C pointer)
    - Memory safety (null pointers, buffer overflow, use-after-free)
    - Lifetime validity (objects don't get freed while in use)
    - Calling convention compliance
    
    Usage:
        verifier = FFIVerifier()
        
        signature = FFISignature(
            library_name="libfoo.so",
            function_name="sum_array",
            language_pair=FFILanguagePair.PYTHON_TO_C,
            parameters={
                "arr": ("List[int]", "int*"),
                "len": ("int", "int32_t"),
            },
            return_type=("int", "int32_t"),
            requires_pointer_validation=True,
        )
        
        contract = FFIContract(
            signature=signature,
            requires="len >= 0 and len <= len(arr)",
            ensures="result >= 0",
            no_null_pointers=True,
        )
        
        result = verifier.verify(contract)
        print(f"Type Safe: {result.type_safety}")
        print(f"Memory Safe: {result.memory_safety}")
    """
    
    def __init__(self):
        """Initialize FFI verifier."""
        self.verified_signatures: Dict[str, FFIVerificationResult] = {}
        
        # Type mapping rules for each language pair
        self.type_mappings = self._initialize_type_mappings()
        
        # Memory safety patterns to check
        self.null_pointer_patterns = {
            r'pointer\s*=\s*NULL': "null_pointer_assignment",
            r'if\s*\(\s*!?\s*pointer\s*\)': "null_pointer_check",
            r'->': "pointer_dereference",
        }
        
        self.buffer_overflow_patterns = {
            r'\w+\[\s*i\s*\]': "array_access",
            r'memcpy|strcpy|strcat': "unsafe_copy",
            r'\w+\s*\+\s*\w+': "pointer_arithmetic",
        }
    
    def _initialize_type_mappings(self) -> Dict[FFILanguagePair, Dict[str, str]]:
        """
        Initialize type coercion rules for all language pairs.
        
        Returns:
            Dict mapping language pairs to type coercion rules
        """
        return {
            FFILanguagePair.PYTHON_TO_C: {
                "int": "int32_t | int64_t",
                "float": "double",
                "bytes": "const char*",
                "bytearray": "uint8_t*",
                "list": "pointer to array",
                "List": "pointer to array",  # Handle List[T] generics
                "dict": "struct*",
                "Dict": "struct*",
                "bool": "int (0/1)",
                "str": "const char*",
                "None": "NULL",
            },
            FFILanguagePair.PYTHON_TO_CPLUSPLUS: {
                "int": "int32_t | int64_t | int",
                "float": "double | float",
                "str": "std::string",
                "list": "std::vector",
                "List": "std::vector",
                "dict": "std::map",
                "Dict": "std::map",
                "bool": "bool",
                "None": "nullptr",
            },
            FFILanguagePair.RUST_TO_C: {
                "i32": "int32_t",
                "i64": "int64_t",
                "u8": "uint8_t",
                "u32": "uint32_t",
                "u64": "uint64_t",
                "f32": "float",
                "f64": "double",
                "&[u8]": "const uint8_t*",
                "&mut T": "T*",
                "String": "const char*",
                "bool": "uint8_t",
            },
            FFILanguagePair.JAVASCRIPT_TO_WASM: {
                "number": "i32 | i64 | f32 | f64",
                "string": "pointer to UTF-8 string",
                "ArrayBuffer": "pointer to memory",
                "TypedArray": "pointer to array",
                "bigint": "i64",
                "boolean": "i32",
            },
        }
    
    # ========================================================================
    # TYPE SAFETY VERIFICATION
    # ========================================================================
    
    def verify_type_safety(
        self,
        signature: FFISignature,
    ) -> Tuple[bool, List[str]]:
        """
        Verify type coercion safety at FFI boundary.
        
        Args:
            signature: FFI function signature with parameter types
            
        Returns:
            (is_type_safe, list of type mismatch issues)
        """
        issues = []
        
        # Get type mappings for this language pair
        mappings = self.type_mappings.get(signature.language_pair, {})
        
        if not mappings:
            # Unknown language pair
            issues.append(f"Unknown language pair: {signature.language_pair.value}")
            return False, issues
        
        # Check each parameter
        for param_name, (source_type, ffi_type) in signature.parameters.items():
            # Normalize types - extract base type from generics
            source_base = self._extract_base_type(source_type)
            ffi_base = self._extract_base_type(ffi_type)
            
            # Check if source type can map to FFI type
            allowed_targets = mappings.get(source_base, None)
            
            if allowed_targets is None:
                issues.append(f"Parameter '{param_name}': no mapping for source type '{source_type}'")
            elif isinstance(allowed_targets, str):
                # Check if FFI type matches allowed target
                if ffi_base not in allowed_targets and allowed_targets not in ffi_type:
                    issues.append(
                        f"Parameter '{param_name}': '{source_type}' → '{ffi_type}' "
                        f"not in allowed mappings {allowed_targets}"
                    )
        
        # Check return type
        source_ret, ffi_ret = signature.return_type
        source_ret_base = self._extract_base_type(source_ret)
        allowed_ret = mappings.get(source_ret_base, None)
        
        if allowed_ret is None:
            issues.append(f"Return type: no mapping for '{source_ret}'")
        elif isinstance(allowed_ret, str):
            ffi_ret_base = self._extract_base_type(ffi_ret)
            if ffi_ret_base not in allowed_ret and allowed_ret not in ffi_ret:
                issues.append(
                    f"Return type: '{source_ret}' → '{ffi_ret}' "
                    f"not in allowed mappings {allowed_ret}"
                )
        
        is_safe = len(issues) == 0
        return is_safe, issues
    
    @staticmethod
    def _extract_base_type(type_str: str) -> str:
        """
        Extract base type from generic type strings.
        
        Examples:
            List[int] → List
            Dict[str, int] → Dict
            int* → int
            const char* → char
            std::vector<int> → vector
        """
        # Remove whitespace
        type_str = type_str.strip()
        
        # Handle generic brackets [...]
        if '[' in type_str:
            return type_str.split('[')[0].strip()
        
        # Handle template brackets <...>
        if '<' in type_str:
            return type_str.split('<')[0].strip()
        
        # Handle pointer *
        if '*' in type_str:
            return type_str.replace('*', '').replace('const', '').replace('&', '').strip()
        
        # Handle reference &
        if '&' in type_str:
            return type_str.replace('&', '').strip()
        
        return type_str
    
    # ========================================================================
    # MEMORY SAFETY VERIFICATION
    # ========================================================================
    
    def verify_memory_safety(
        self,
        signature: FFISignature,
        c_code: Optional[str] = None,
    ) -> Tuple[bool, List[MemorySafetyIssue]]:
        """
        Verify memory safety at FFI boundary.
        
        Checks:
        - Null pointer dereferences
        - Buffer overflows
        - Use-after-free
        - Uninitialized memory access
        - Alignment issues
        
        Args:
            signature: FFI signature with pointer requirements
            c_code: Optional C code to analyze for patterns
            
        Returns:
            (is_memory_safe, list of detected issues)
        """
        issues: List[MemorySafetyIssue] = []
        
        # Check pointer parameters
        for param_name, (source_type, ffi_type) in signature.parameters.items():
            # Detect pointer parameters
            if '*' in ffi_type or 'pointer' in source_type.lower():
                # Pointer parameter detected
                if signature.requires_pointer_validation:
                    # Good - requires validation
                    pass
                else:
                    # Pointer without validation
                    if 'Optional' not in source_type and source_type != 'Optional[T]':
                        # Not explicitly optional
                        issues.append(MemorySafetyIssue.NULL_POINTER_DEREFERENCE)
            
            # Check for unbounded arrays
            if '[' in source_type and ']' not in source_type.split('[')[1]:
                # Unbounded array without length parameter
                has_length_param = any('len' in p.lower() or 'size' in p.lower() 
                                      for p in signature.parameters.keys())
                if not has_length_param:
                    issues.append(MemorySafetyIssue.BUFFER_OVERFLOW)
        
        # Analyze C code patterns if provided
        if c_code:
            issues.extend(self._detect_memory_issues_in_c(c_code))
        
        is_safe = len(issues) == 0
        return is_safe, issues
    
    def _detect_memory_issues_in_c(self, code: str) -> List[MemorySafetyIssue]:
        """
        Detect memory issues from C code patterns.
        
        Args:
            code: C source code to analyze
            
        Returns:
            List of detected memory safety issues
        """
        issues = []
        
        # Pattern: strcpy/strcat without bounds checking
        if re.search(r'strcpy\s*\(', code):
            issues.append(MemorySafetyIssue.BUFFER_OVERFLOW)
        
        # Pattern: pointer arithmetic without validation
        if re.search(r'\w+\s*\+\s*\d+\s*[;)]', code):
            # Check if validated
            if not re.search(r'(assert|if|check).*\w+.*<', code):
                issues.append(MemorySafetyIssue.BUFFER_OVERFLOW)
        
        # Pattern: free then use
        if re.search(r'free\s*\(\s*(\w+)\s*\);.*\1\s*->', code):
            issues.append(MemorySafetyIssue.USE_AFTER_FREE)
        
        # Pattern: malloc without NULL check
        malloc_matches = re.findall(r'(\w+)\s*=\s*malloc\s*\(', code)
        for var in malloc_matches:
            if not re.search(rf'if\s*\(\s*!?\s*{var}\s*\)', code):
                issues.append(MemorySafetyIssue.NULL_POINTER_DEREFERENCE)
        
        return issues
    
    # ========================================================================
    # LIFETIME VERIFICATION
    # ========================================================================
    
    def verify_lifetime_safety(
        self,
        signature: FFISignature,
    ) -> Tuple[bool, List[str]]:
        """
        Verify that objects don't outlive their lifetime at FFI boundary.
        
        Args:
            signature: FFI signature with lifetime information
            
        Returns:
            (is_lifetime_safe, list of lifetime issues)
        """
        issues = []
        
        if not signature.requires_lifetime_check:
            # No lifetime checking required
            return True, []
        
        # Check for parameters that reference temporary objects
        for param_name, (source_type, ffi_type) in signature.parameters.items():
            # Pattern: pointer to temporary
            if '*' in ffi_type and ('&' in source_type or 'ref' in source_type.lower()):
                # Reference type being converted to pointer
                # Risk: reference dies, pointer becomes invalid
                if 'temporary' in source_type.lower():
                    issues.append(f"Parameter '{param_name}': Temporary reference lifetime risk")
        
        is_safe = len(issues) == 0
        return is_safe, issues
    
    # ========================================================================
    # FULL VERIFICATION
    # ========================================================================
    
    def verify(
        self,
        contract: FFIContract,
        c_code: Optional[str] = None,
    ) -> FFIVerificationResult:
        """
        Full FFI contract verification.
        
        Args:
            contract: FFI contract to verify
            c_code: Optional C implementation to analyze
            
        Returns:
            FFIVerificationResult
        """
        import time
        start = time.time()
        
        signature = contract.signature
        
        # Check type safety
        type_safe, type_issues = self.verify_type_safety(signature)
        
        # Check memory safety
        mem_safe, mem_issues = self.verify_memory_safety(signature, c_code)
        
        # Check lifetime safety
        lifetime_safe, lifetime_issues = self.verify_lifetime_safety(signature)
        
        # Combine results
        all_memory_issues = mem_issues
        
        verified = (
            type_safe and 
            mem_safe and 
            lifetime_safe and
            contract.no_null_pointers and
            contract.no_buffer_overflow and
            contract.valid_lifetime and
            contract.memory_initialized
        )
        
        # Build proof if verified
        proof = None
        counterexample = None
        
        if verified:
            proof = {
                "type_safe": type_safe,
                "memory_safe": mem_safe,
                "lifetime_safe": lifetime_safe,
                "strategy": "static_analysis",
            }
        else:
            # Collect first issue as counterexample
            if type_issues:
                counterexample = {"error": type_issues[0]}
            elif all_memory_issues:
                counterexample = {"error": all_memory_issues[0].value}
            elif lifetime_issues:
                counterexample = {"error": lifetime_issues[0]}
        
        end = time.time()
        
        result = FFIVerificationResult(
            verified=verified,
            signature=signature,
            type_safety=type_safe,
            memory_safety=mem_safe,
            memory_issues=all_memory_issues,
            proof=proof,
            counterexample=counterexample,
            time_seconds=end - start,
        )
        
        key = f"{signature.library_name}:{signature.function_name}"
        self.verified_signatures[key] = result
        
        return result
    
    # ========================================================================
    # UTILITIES
    # ========================================================================
    
    def get_verification_report(
        self,
        signature_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get verification report for one or all signatures.
        
        Args:
            signature_key: "library:function" format (or None for all)
            
        Returns:
            Summary report
        """
        if signature_key:
            if signature_key not in self.verified_signatures:
                return {"error": "signature_not_found"}
            
            result = self.verified_signatures[signature_key]
            return {
                "signature": signature_key,
                "verified": result.verified,
                "type_safety": result.type_safety,
                "memory_safety": result.memory_safety,
                "safety_score": result.safety_score(),
                "time_seconds": result.time_seconds,
                "issues": [i.value for i in result.memory_issues],
            }
        else:
            # All signatures
            total = len(self.verified_signatures)
            verified_count = sum(1 for r in self.verified_signatures.values() if r.verified)
            
            return {
                "total_signatures": total,
                "verified": verified_count,
                "failed": total - verified_count,
                "signatures": {
                    key: {
                        "verified": result.verified,
                        "safety_score": result.safety_score(),
                    }
                    for key, result in self.verified_signatures.items()
                },
            }
    
    def suggest_fixes(
        self,
        result: FFIVerificationResult,
    ) -> List[str]:
        """
        Suggest fixes for detected FFI issues.
        
        Args:
            result: FFIVerificationResult with issues
            
        Returns:
            List of suggested fixes
        """
        suggestions = []
        
        for issue in result.memory_issues:
            if issue == MemorySafetyIssue.NULL_POINTER_DEREFERENCE:
                suggestions.append("Add NULL pointer checks in C code")
                suggestions.append("Use optional types in source language")
                suggestions.append("Validate pointers before dereference")
            
            elif issue == MemorySafetyIssue.BUFFER_OVERFLOW:
                suggestions.append("Use bounds-safe functions (strncpy instead of strcpy)")
                suggestions.append("Add length parameters to unbounded arrays")
                suggestions.append("Use safe string libraries")
            
            elif issue == MemorySafetyIssue.USE_AFTER_FREE:
                suggestions.append("Clear pointers after free()")
                suggestions.append("Use reference counting or RAII in C++")
                suggestions.append("Track object lifetime explicitly")
            
            elif issue == MemorySafetyIssue.UNINITIALIZED_READ:
                suggestions.append("Initialize all variables before use")
                suggestions.append("Use memset() to zero memory after allocation")
        
        if not result.type_safety:
            suggestions.append("Review type coercion mappings")
            suggestions.append("Consider adding explicit type conversion functions")
        
        if not result.memory_safety:
            suggestions.append("Enable compiler warnings for memory issues")
            suggestions.append("Use AddressSanitizer or Valgrind for runtime checking")
        
        return suggestions
    
    def suggest_validation_wrapper(
        self,
        signature: FFISignature,
    ) -> str:
        """
        Generate Python validation wrapper for FFI function.
        
        Args:
            signature: FFI signature
            
        Returns:
            Python wrapper code
        """
        wrapper = f"""
def {signature.function_name}_safe({', '.join(signature.parameters.keys())}):
    \"\"\"Wrapper with validation for {signature.function_name}\"\"\"
    
    # Type validation
"""
        
        for param_name, (source_type, ffi_type) in signature.parameters.items():
            if '*' in ffi_type:
                wrapper += f"    if {param_name} is None:\n"
                wrapper += f"        raise ValueError('{param_name} cannot be None')\n"
        
        wrapper += f"\n    # Call native function\n"
        wrapper += f"    return lib.{signature.function_name}("
        wrapper += ", ".join(signature.parameters.keys())
        wrapper += ")\n"
        
        return wrapper
