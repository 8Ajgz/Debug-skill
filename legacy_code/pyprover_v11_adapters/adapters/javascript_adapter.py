"""
PyProver JavaScript Adapter

Implements LanguageAdapter for JavaScript.
Uses regex-based parsing (fallback mode) and JSDoc comment extraction.
For production use, integrate with @babel/parser via subprocess.
"""

import re
import json
import subprocess
import z3
from typing import Dict, List, Any, Optional
from ..interfaces import LanguageAdapter, Contract


class JavaScriptAdapter(LanguageAdapter):
    """Adapter for JavaScript code verification"""
    
    @property
    def language_name(self) -> str:
        return 'javascript'
    
    def parse_function(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """
        Parse JavaScript code and extract function.
        
        Tries Babel parser first, falls back to regex parsing.
        
        Args:
            source_code: JavaScript source code
            func_name: Name of function to extract
        
        Returns:
            Dictionary with 'ast', 'source', and 'language' keys
        """
        # Try Babel parser first
        try:
            return self._parse_with_babel(source_code, func_name)
        except:
            # Fallback to regex parsing
            return self._parse_with_regex(source_code, func_name)
    
    def _parse_with_babel(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """Parse JavaScript using Babel AST parser"""
        escaped_code = json.dumps(source_code)
        
        babel_script = f"""
const parser = require('@babel/parser');
const code = {escaped_code};

try {{
    const ast = parser.parse(code, {{
        sourceType: 'module',
        allowImportExportEverywhere: true,
        allowReturnOutsideFunction: true
    }});
    console.log(JSON.stringify(ast));
}} catch (e) {{
    console.error(e.message);
    process.exit(1);
}}
"""
        
        result = subprocess.run(
            ['node', '-e', babel_script],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            raise SyntaxError(f"JavaScript parse error: {result.stderr}")
        
        ast_json = json.loads(result.stdout)
        
        # Find function in AST
        func_node = self._find_function_in_ast(ast_json, func_name)
        if not func_node:
            raise ValueError(f"Function '{func_name}' not found")
        
        return {
            'ast': func_node,
            'source': source_code,
            'language': 'javascript',
            'full_ast': ast_json
        }
    
    def _parse_with_regex(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """Fallback: Parse JavaScript using regex"""
        
        # Pattern for function declaration or const/let assignment
        patterns = [
            rf'function\s+{re.escape(func_name)}\s*\(',
            rf'const\s+{re.escape(func_name)}\s*=\s*(?:async\s*)?\(',
            rf'let\s+{re.escape(func_name)}\s*=\s*(?:async\s*)?\(',
            rf'var\s+{re.escape(func_name)}\s*=\s*(?:async\s*)?\(',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, source_code)
            if match:
                return {
                    'ast': {'name': func_name, 'type': 'FunctionExpression'},
                    'source': source_code,
                    'language': 'javascript'
                }
        
        raise ValueError(f"Function '{func_name}' not found in JavaScript code")
    
    def extract_contracts(self, ast_data: Dict[str, Any]) -> Contract:
        """
        Extract JSDoc comments with @requires, @ensures, @assume.
        
        Example:
            /**
             * @requires arr.length > 0
             * @ensures result >= 0
             */
            function findMax(arr) { ... }
        """
        contracts = Contract(
            requires=[],
            ensures=[],
            assumes=[],
            template_type=None,
            state_tracking={}
        )
        
        source = ast_data.get('source', '')
        func_name = ast_data.get('ast', {}).get('name', '')
        
        # Find JSDoc comment before function
        jsdoc = self._extract_jsdoc(source, func_name)
        
        if jsdoc:
            # Extract @requires
            requires_matches = re.findall(r'@requires\s+(.+?)(?=\n|@|$)', jsdoc)
            contracts.requires = [m.strip() for m in requires_matches]
            
            # Extract @ensures
            ensures_matches = re.findall(r'@ensures\s+(.+?)(?=\n|@|$)', jsdoc)
            contracts.ensures = [m.strip() for m in ensures_matches]
            
            # Extract @assume
            assume_matches = re.findall(r'@assume(?:s)?\s+(.+?)(?=\n|@|$)', jsdoc)
            contracts.assumes = [m.strip() for m in assume_matches]
        
        return contracts
    
    def extract_variables(self, ast_data: Dict[str, Any]) -> List[str]:
        """
        Extract all variables from JavaScript function.
        
        Finds: parameters, let/const/var declarations, identifiers.
        """
        variables = set()
        source = ast_data.get('source', '')
        
        # Extract function parameters
        func_pattern = r'function\s+\w+\s*\(([^)]*)\)|const\s+\w+\s*=\s*\(([^)]*)\)'
        match = re.search(func_pattern, source)
        if match:
            params = match.group(1) or match.group(2)
            for param in params.split(','):
                param = param.strip()
                if param and ':' not in param:  # Exclude TypeScript types
                    # Get just the parameter name
                    name = re.match(r'(\w+)', param)
                    if name:
                        variables.add(name.group(1))
        
        # Extract variable declarations
        var_patterns = [
            r'(?:let|const|var)\s+(\w+)',
            r'this\.(\w+)\s*=',
            r'(\w+)\s*='
        ]
        
        for pattern in var_patterns:
            matches = re.findall(pattern, source)
            variables.update(matches)
        
        return list(variables)
    
    def extract_loops(self, ast_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract for, while, for...of, for...in loops from JavaScript.
        """
        loops = []
        source = ast_data.get('source', '')
        
        # Find for loops
        for_matches = re.finditer(r'for\s*\(\s*(.+?);(.+?);(.+?)\)', source)
        for match in for_matches:
            loops.append({
                'type': 'for',
                'init': match.group(1),
                'test': match.group(2),
                'update': match.group(3)
            })
        
        # Find while loops
        while_matches = re.finditer(r'while\s*\((.+?)\)', source)
        for match in while_matches:
            loops.append({
                'type': 'while',
                'test': match.group(1)
            })
        
        # Find for...of loops
        forof_matches = re.finditer(r'for\s*\((?:let|const|var)\s+(\w+)\s+of\s+(.+?)\)', source)
        for match in forof_matches:
            loops.append({
                'type': 'for...of',
                'variable': match.group(1),
                'iterable': match.group(2)
            })
        
        return loops
    
    def infer_template(self, ast_data: Dict[str, Any]) -> Optional[str]:
        """
        Detect verification template from JavaScript patterns.
        """
        source = ast_data.get('source', '')
        
        # Check for ACCUMULATOR pattern
        if self._matches_accumulator(source):
            return 'ACCUMULATOR'
        
        # Check for BINARY_SEARCH pattern
        if self._matches_binary_search(source):
            return 'BINARY_SEARCH'
        
        # Check for MIN_MAX pattern
        if self._matches_min_max(source):
            return 'MIN_MAX_LOOP'
        
        # Check for FILTER pattern
        if self._matches_filter(source):
            return 'FILTER'
        
        return None
    
    def map_type_to_z3(self, type_hint: str) -> Any:
        """
        Map JavaScript/JSDoc types to Z3 sorts.
        
        Since JS is dynamically typed, use conservative defaults.
        JSDoc hints: {number}, {string}, {boolean}, {Array}
        """
        if not type_hint:
            return z3.IntSort()
        
        type_lower = type_hint.lower().strip()
        
        # Remove JSDoc brackets
        if '{' in type_lower:
            type_lower = type_lower.strip('{}')
        
        type_map = {
            'number': z3.IntSort(),
            'int': z3.IntSort(),
            'integer': z3.IntSort(),
            'string': z3.StringSort(),
            'str': z3.StringSort(),
            'boolean': z3.BoolSort(),
            'bool': z3.BoolSort(),
            'array': z3.ArraySort(z3.IntSort(), z3.IntSort()),
            'object': z3.ArraySort(z3.StringSort(), z3.IntSort()),
        }
        
        return type_map.get(type_lower, z3.IntSort())
    
    # Helper methods
    
    def _extract_jsdoc(self, source: str, func_name: str) -> Optional[str]:
        """Extract JSDoc comment before function"""
        
        # Find function position
        func_patterns = [
            f'function {func_name}',
            f'const {func_name} =',
            f'let {func_name} =',
            f'var {func_name} ='
        ]
        
        func_pos = -1
        for pattern in func_patterns:
            pos = source.find(pattern)
            if pos != -1:
                func_pos = pos
                break
        
        if func_pos == -1:
            return None
        
        # Look for JSDoc before function
        before = source[:func_pos]
        jsdoc_match = re.findall(r'/\*\*[\s\S]*?\*/', before)
        
        if jsdoc_match:
            return jsdoc_match[-1]  # Return last JSDoc
        
        return None
    
    def _matches_accumulator(self, source: str) -> bool:
        """Check for ACCUMULATOR pattern"""
        has_init = bool(re.search(r'(sum|result|product|count)\s*=\s*[0-9]', source))
        has_update = bool(re.search(r'(sum|result|product|count)\s*\+=', source))
        return has_init and has_update
    
    def _matches_binary_search(self, source: str) -> bool:
        """Check for BINARY_SEARCH pattern"""
        has_left_right = bool(re.search(r'(left|right)\s*=', source))
        has_while = 'while' in source
        has_mid = 'mid' in source
        return has_left_right and has_while and has_mid
    
    def _matches_min_max(self, source: str) -> bool:
        """Check for MIN_MAX_LOOP pattern"""
        has_init = bool(re.search(r'(min|max)Val\s*=', source))
        has_compare = bool(re.search(r'if\s*\(.*[<>]', source))
        return has_init and has_compare
    
    def _matches_filter(self, source: str) -> bool:
        """Check for FILTER pattern"""
        has_counter = bool(re.search(r'(count|counter)\s*=\s*0', source))
        has_increment = bool(re.search(r'(count|counter)\s*\+=', source))
        return has_counter and has_increment
    
    def _find_function_in_ast(self, ast_json: Dict, func_name: str) -> Optional[Dict]:
        """Find function node in Babel AST (if available)"""
        
        def traverse(node):
            if not node:
                return None
            
            if isinstance(node, dict):
                if node.get('type') == 'FunctionDeclaration':
                    if node.get('id', {}).get('name') == func_name:
                        return node
                
                for value in node.values():
                    result = traverse(value)
                    if result:
                        return result
            
            elif isinstance(node, list):
                for item in node:
                    result = traverse(item)
                    if result:
                        return result
            
            return None
        
        return traverse(ast_json)
