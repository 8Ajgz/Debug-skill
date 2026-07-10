"""
PyProver Core - Language-Agnostic Verifier

Main verification engine that uses language adapters.
Orchestrates parsing, contract extraction, and Z3 verification.
"""

import time
import z3
from typing import Dict, List, Any, Optional
from .interfaces import LanguageAdapter, Contract, VerificationResult
from .z3_verifier import Z3Verifier


class PyProverCore:
    """
    Core verification engine that is language-agnostic.
    
    Works with any LanguageAdapter to verify code in Python, JavaScript, TypeScript, etc.
    """
    
    def __init__(self, adapter: LanguageAdapter):
        """
        Initialize with a language adapter.
        
        Args:
            adapter: Implementation of LanguageAdapter for specific language
        """
        self.adapter = adapter
        self.z3_verifier = Z3Verifier()
    
    def verify(self, source_code: str, func_name: str) -> VerificationResult:
        """
        Verify a function in the source code.
        
        Args:
            source_code: Source code containing the function
            func_name: Name of function to verify
        
        Returns:
            VerificationResult with verification status and details
        """
        start_time = time.time()
        
        try:
            # Step 1: Parse function (language-specific)
            ast_data = self.adapter.parse_function(source_code, func_name)
            
            # Step 2: Extract contracts (language-specific)
            contracts = self.adapter.extract_contracts(ast_data)
            
            # Step 3: Extract variables (language-specific)
            variables = self.adapter.extract_variables(ast_data)
            
            # Step 4: Infer template type (language-specific)
            template_type = self.adapter.infer_template(ast_data)
            
            # Step 5: Build Z3 variables (shared logic)
            z3_vars = self._build_z3_variables(variables, ast_data)
            
            # Step 6: Verify using Z3 (shared engine)
            verified, proof, counterexample = self.z3_verifier.verify(
                contracts,
                z3_vars,
                template_type
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            return VerificationResult(
                verified=verified,
                function_name=func_name,
                language=self.adapter.language_name,
                template_type=template_type,
                proof=proof,
                counterexample=counterexample,
                duration_ms=duration_ms
            )
        
        except SyntaxError as e:
            duration_ms = (time.time() - start_time) * 1000
            return VerificationResult(
                verified=False,
                function_name=func_name,
                language=self.adapter.language_name,
                error=f"Parse error: {str(e)}",
                duration_ms=duration_ms
            )
        
        except ValueError as e:
            duration_ms = (time.time() - start_time) * 1000
            return VerificationResult(
                verified=False,
                function_name=func_name,
                language=self.adapter.language_name,
                error=f"Value error: {str(e)}",
                duration_ms=duration_ms
            )
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return VerificationResult(
                verified=False,
                function_name=func_name,
                language=self.adapter.language_name,
                error=f"Verification error: {str(e)}",
                duration_ms=duration_ms
            )
    
    def _build_z3_variables(self, variables: List[str], ast_data: Dict[str, Any]) -> Dict[str, z3.ExprRef]:
        """
        Build Z3 variables from extracted variable names.
        
        Args:
            variables: List of variable names from adapter
            ast_data: AST data (may contain type information)
        
        Returns:
            Dictionary mapping variable names to Z3 variables
        """
        z3_vars = {}
        
        for var in variables:
            # Default to IntSort unless we have type information
            z3_vars[var] = z3.Int(var)
        
        # Add special variables
        z3_vars['result'] = z3.Int('result')  # For @ensures clauses
        z3_vars['True'] = z3.BoolVal(True)
        z3_vars['False'] = z3.BoolVal(False)
        
        # Add length variables for arrays
        for var in variables:
            z3_vars[f'z3_len_{var}'] = z3.Int(f'z3_len_{var}')
        
        return z3_vars
    
    def batch_verify(self, source_code: str, func_names: List[str]) -> List[VerificationResult]:
        """
        Verify multiple functions in source code.
        
        Args:
            source_code: Source code
            func_names: List of function names to verify
        
        Returns:
            List of VerificationResult objects
        """
        results = []
        for func_name in func_names:
            result = self.verify(source_code, func_name)
            results.append(result)
        return results
    
    def get_template_info(self, ast_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get information about detected template"""
        template = self.adapter.infer_template(ast_data)
        
        return {
            'template': template,
            'description': self._get_template_description(template)
        }
    
    def _get_template_description(self, template: Optional[str]) -> str:
        """Get human-readable description of template"""
        descriptions = {
            'ACCUMULATOR': 'Running sum/product pattern',
            'BINARY_SEARCH': 'Binary search with invariants',
            'RECURSION': 'Recursive function with structural induction',
            'STATE_MACHINE': 'State transition verification',
            'MIN_MAX_LOOP': 'Finding minimum/maximum values',
            'FILTER': 'Counting matching elements',
            'SCAN': 'Cumulative operations',
            'SORTED_ARRAY': 'Sorting and maintaining sorted state',
            'PARTITION': 'Array partitioning (quicksort)',
            'PERMUTATION': 'Verifying result is permutation of input'
        }
        
        return descriptions.get(template, 'Unknown pattern')
