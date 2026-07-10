"""
PyProver Python Adapter

Implements LanguageAdapter for Python.
Parses Python code using AST module, extracts decorators, detects patterns.
"""

import ast
import re
import z3
from typing import Dict, List, Any, Optional
from ..interfaces import LanguageAdapter, Contract


class PythonAdapter(LanguageAdapter):
    """Adapter for Python code verification"""
    
    @property
    def language_name(self) -> str:
        return 'python'
    
    def parse_function(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """
        Parse Python source code and extract function AST.
        
        Args:
            source_code: Python source code
            func_name: Name of function to extract
        
        Returns:
            Dictionary with 'ast', 'source', and 'language' keys
        
        Raises:
            SyntaxError: If code is not valid Python
            ValueError: If function not found
        """
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            raise SyntaxError(f"Invalid Python code: {e}")
        
        # Find function in AST
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                return {
                    'ast': node,
                    'source': source_code,
                    'language': 'python'
                }
        
        raise ValueError(f"Function '{func_name}' not found in Python code")
    
    def extract_contracts(self, ast_data: Dict[str, Any]) -> Contract:
        """
        Extract @requires, @ensures, @assume decorators from function.
        
        Example:
            @requires("len(arr) > 0")
            @ensures("result >= 0")
            def find_max(arr):
                ...
        """
        contracts = Contract(
            requires=[],
            ensures=[],
            assumes=[],
            template_type=None,
            state_tracking={}
        )
        
        func_node = ast_data.get('ast')
        if not isinstance(func_node, ast.FunctionDef):
            return contracts
        
        # Extract contracts from decorators
        for decorator in func_node.decorator_list:
            if isinstance(decorator, ast.Call):
                # Get function name
                func_name = None
                if isinstance(decorator.func, ast.Name):
                    func_name = decorator.func.id
                elif isinstance(decorator.func, ast.Attribute):
                    func_name = decorator.func.attr
                
                # Extract contract text
                if func_name and decorator.args:
                    try:
                        contract_text = ast.literal_eval(decorator.args[0])
                        
                        if func_name == 'requires':
                            contracts.requires.append(contract_text)
                        elif func_name == 'ensures':
                            contracts.ensures.append(contract_text)
                        elif func_name == 'assume':
                            contracts.assumes.append(contract_text)
                        elif func_name == 'state_tracking':
                            # @state_tracking('arr', 'count')
                            for arg in decorator.args:
                                if isinstance(arg, ast.Constant):
                                    contracts.state_tracking[arg.value] = arg.value
                    except (ValueError, TypeError):
                        pass
        
        return contracts
    
    def extract_variables(self, ast_data: Dict[str, Any]) -> List[str]:
        """
        Extract all variables from function.
        
        Finds: local variables, parameters, assignments, etc.
        """
        variables = set()
        func_node = ast_data.get('ast')
        
        if not isinstance(func_node, ast.FunctionDef):
            return []
        
        # Add function parameters
        for arg in func_node.args.args:
            variables.add(arg.arg)
        
        # Add local variables (assignments)
        for node in ast.walk(func_node):
            if isinstance(node, ast.Name):
                variables.add(node.id)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        variables.add(target.id)
            elif isinstance(node, ast.AugAssign):
                if isinstance(node.target, ast.Name):
                    variables.add(node.target.id)
        
        return list(variables)
    
    def extract_loops(self, ast_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract for, while loops from function.
        
        Returns loop information for pattern matching.
        """
        loops = []
        func_node = ast_data.get('ast')
        
        if not isinstance(func_node, ast.FunctionDef):
            return []
        
        for node in ast.walk(func_node):
            if isinstance(node, ast.For):
                loops.append({
                    'type': 'for',
                    'target': self._ast_to_str(node.target),
                    'iter': self._ast_to_str(node.iter),
                    'body': node.body
                })
            elif isinstance(node, ast.While):
                loops.append({
                    'type': 'while',
                    'test': self._ast_to_str(node.test),
                    'body': node.body
                })
        
        return loops
    
    def infer_template(self, ast_data: Dict[str, Any]) -> Optional[str]:
        """
        Detect verification template from Python code patterns.
        
        Returns: 'ACCUMULATOR', 'BINARY_SEARCH', 'MIN_MAX_LOOP', 'FILTER', etc.
        """
        source = ast_data.get('source', '')
        func_node = ast_data.get('ast')
        
        if not isinstance(func_node, ast.FunctionDef):
            return None
        
        # Get function source as string
        func_source = self._ast_to_str(func_node)
        
        # Check for ACCUMULATOR pattern: result = 0; for/while loop; result +=
        if self._matches_accumulator(func_source, func_node):
            return 'ACCUMULATOR'
        
        # Check for BINARY_SEARCH pattern: left/right pointers, while loop
        if self._matches_binary_search(func_source, func_node):
            return 'BINARY_SEARCH'
        
        # Check for MIN_MAX pattern
        if self._matches_min_max(func_source, func_node):
            return 'MIN_MAX_LOOP'
        
        # Check for FILTER pattern: counter incremented in if
        if self._matches_filter(func_source, func_node):
            return 'FILTER'
        
        # Check for RECURSION pattern
        if self._is_recursive(func_node):
            return 'RECURSION'
        
        return None
    
    def map_type_to_z3(self, type_hint: str) -> Any:
        """
        Map Python type hints to Z3 sorts.
        
        Examples: int → IntSort, str → StringSort, List[int] → ArraySort
        """
        if not type_hint:
            return z3.IntSort()
        
        type_lower = type_hint.lower().strip()
        
        # Handle typing module types
        type_map = {
            'int': z3.IntSort(),
            'float': z3.RealSort(),
            'bool': z3.BoolSort(),
            'boolean': z3.BoolSort(),
            'str': z3.StringSort(),
            'string': z3.StringSort(),
            'list': z3.ArraySort(z3.IntSort(), z3.IntSort()),
            'dict': z3.ArraySort(z3.StringSort(), z3.IntSort()),
            'set': z3.ArraySort(z3.IntSort(), z3.BoolSort()),
        }
        
        return type_map.get(type_lower, z3.IntSort())
    
    # Helper methods
    
    def _ast_to_str(self, node: Any) -> str:
        """Convert AST node to source string"""
        try:
            return ast.unparse(node)
        except AttributeError:
            # Python < 3.9
            return str(node)
    
    def _matches_accumulator(self, source: str, func_node: ast.FunctionDef) -> bool:
        """Check if code matches ACCUMULATOR pattern"""
        # Pattern: result/sum initialized; for/while loop; result += arr[i]
        
        # Look for accumulator-like initialization and update
        has_init = bool(re.search(r'(result|sum|product|count)\s*=\s*[0-9]', source))
        has_update = bool(re.search(r'(result|sum|product|count)\s*\+=', source))
        
        return has_init and has_update
    
    def _matches_binary_search(self, source: str, func_node: ast.FunctionDef) -> bool:
        """Check if code matches BINARY_SEARCH pattern"""
        # Pattern: left=0, right=len-1; while left<=right; mid calculation
        
        has_left_right = bool(re.search(r'(left|right)\s*=', source))
        has_while = 'while' in source
        has_mid = 'mid' in source or 'middle' in source
        
        return has_left_right and has_while and has_mid
    
    def _matches_min_max(self, source: str, func_node: ast.FunctionDef) -> bool:
        """Check if code matches MIN_MAX_LOOP pattern"""
        # Pattern: min/max initialized; comparison in if
        
        has_min_max = bool(re.search(r'(min_val|minVal|max_val|maxVal)\s*=', source))
        has_comparison = bool(re.search(r'(if|elif).*[<>]', source))
        has_update = bool(re.search(r'(min_val|minVal|max_val|maxVal)\s*=', source))
        
        return has_min_max and has_comparison and has_update
    
    def _matches_filter(self, source: str, func_node: ast.FunctionDef) -> bool:
        """Check if code matches FILTER pattern"""
        # Pattern: counter initialized; if condition with counter +=
        
        has_counter = bool(re.search(r'(count|counter)\s*=\s*0', source))
        has_increment = bool(re.search(r'(count|counter)\s*\+=', source))
        has_if = 'if' in source
        
        return has_counter and has_increment and has_if
    
    def _is_recursive(self, func_node: ast.FunctionDef) -> bool:
        """Check if function is recursive"""
        func_name = func_node.name
        
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == func_name:
                    return True
        
        return False
