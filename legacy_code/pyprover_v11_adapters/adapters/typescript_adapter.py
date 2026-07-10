"""
PyProver TypeScript Adapter

Implements LanguageAdapter for TypeScript.
Extends JavaScriptAdapter with type hint support.
"""

import re
import json
import subprocess
import z3
from typing import Dict, List, Any, Optional
from .javascript_adapter import JavaScriptAdapter
from ..interfaces import Contract


class TypeScriptAdapter(JavaScriptAdapter):
    """Adapter for TypeScript code verification - extends JavaScript"""
    
    @property
    def language_name(self) -> str:
        return 'typescript'
    
    def parse_function(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """
        Parse TypeScript code with type information.
        
        Tries Babel with TypeScript plugin first, falls back to regex.
        """
        try:
            return self._parse_with_typescript_babel(source_code, func_name)
        except:
            # Fallback to regex parsing
            return self._parse_with_regex(source_code, func_name)
    
    def _parse_with_typescript_babel(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """Parse TypeScript using Babel with TypeScript plugin"""
        escaped_code = json.dumps(source_code)
        
        babel_script = f"""
const parser = require('@babel/parser');
const code = {escaped_code};

try {{
    const ast = parser.parse(code, {{
        sourceType: 'module',
        plugins: ['typescript'],
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
            raise SyntaxError(f"TypeScript parse error: {result.stderr}")
        
        ast_json = json.loads(result.stdout)
        
        # Find function in AST
        func_node = self._find_function_in_ast(ast_json, func_name)
        if not func_node:
            raise ValueError(f"Function '{func_name}' not found")
        
        return {
            'ast': func_node,
            'source': source_code,
            'language': 'typescript',
            'full_ast': ast_json,
            'return_type': self._extract_return_type(func_node),
            'param_types': self._extract_param_types(func_node)
        }
    
    def extract_contracts(self, ast_data: Dict[str, Any]) -> Contract:
        """
        Extract contracts from JSDoc AND TypeScript decorators.
        
        TypeScript can use:
        - JSDoc: /** @requires arr.length > 0 */
        - Type hints: function findMin(arr: number[]): number
        - Decorators: @Requires(...) if available
        """
        # Get JSDoc contracts from parent
        contracts = super().extract_contracts(ast_data)
        
        # Enhanced with TypeScript type information
        source = ast_data.get('source', '')
        
        # Look for TypeScript decorator syntax
        decorator_requires = re.findall(r'@Requires\(\s*["\'](.+?)["\']\s*\)', source)
        decorator_ensures = re.findall(r'@Ensures\(\s*["\'](.+?)["\']\s*\)', source)
        
        contracts.requires.extend(decorator_requires)
        contracts.ensures.extend(decorator_ensures)
        
        return contracts
    
    def extract_variables(self, ast_data: Dict[str, Any]) -> List[str]:
        """
        Extract variables with TypeScript type information.
        """
        variables = super().extract_variables(ast_data)
        
        # TypeScript provides type hints - these are more useful for inference
        source = ast_data.get('source', '')
        
        # Extract typed variables: let x: number = 5
        typed_vars = re.findall(r'(?:let|const|var)\s+(\w+)\s*:\s*\w+', source)
        variables.extend(typed_vars)
        
        return list(set(variables))  # Remove duplicates
    
    def map_type_to_z3(self, type_hint: str) -> Any:
        """
        Map TypeScript types to Z3 sorts - more precise than JavaScript.
        
        TypeScript provides explicit type information.
        Examples:
        - number: IntSort
        - string: StringSort
        - boolean: BoolSort
        - number[]: ArraySort
        - Record<string, number>: ArraySort
        - void: (special handling)
        """
        if not type_hint:
            return z3.IntSort()
        
        type_lower = type_hint.lower().strip()
        
        # Remove generic brackets for base type
        base_type = re.sub(r'<.*?>', '', type_lower)
        base_type = base_type.split('[')[0].strip()
        
        # TypeScript type mappings (more complete than JavaScript)
        type_map = {
            # Primitives
            'number': z3.IntSort(),
            'string': z3.StringSort(),
            'boolean': z3.BoolSort(),
            'bigint': z3.IntSort(),
            'symbol': z3.StringSort(),
            'void': z3.IntSort(),  # Approximation
            'null': z3.IntSort(),  # Approximation
            'undefined': z3.IntSort(),  # Approximation
            'any': z3.IntSort(),  # Default to int
            'unknown': z3.IntSort(),  # Default to int
            
            # Arrays
            'array': z3.ArraySort(z3.IntSort(), z3.IntSort()),
            'number[]': z3.ArraySort(z3.IntSort(), z3.IntSort()),
            'string[]': z3.ArraySort(z3.IntSort(), z3.StringSort()),
            'boolean[]': z3.ArraySort(z3.IntSort(), z3.BoolSort()),
            
            # Objects and Records
            'object': z3.ArraySort(z3.StringSort(), z3.IntSort()),
            'record': z3.ArraySort(z3.StringSort(), z3.IntSort()),
            'map': z3.ArraySort(z3.StringSort(), z3.IntSort()),
            'set': z3.ArraySort(z3.IntSort(), z3.BoolSort()),
        }
        
        return type_map.get(base_type, z3.IntSort())
    
    def get_function_metadata(self, ast_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract function metadata including TypeScript type information.
        """
        metadata = super().get_function_metadata(ast_data)
        
        # Add TypeScript-specific metadata
        metadata['return_type'] = ast_data.get('return_type')
        metadata['param_types'] = ast_data.get('param_types', {})
        
        return metadata
    
    # TypeScript-specific helper methods
    
    def _extract_return_type(self, func_node: Dict[str, Any]) -> Optional[str]:
        """Extract return type annotation from TypeScript function"""
        if not isinstance(func_node, dict):
            return None
        
        return_type = func_node.get('returnType', {})
        
        if isinstance(return_type, dict):
            type_annotation = return_type.get('typeAnnotation', {})
            
            if type_annotation.get('type') == 'Identifier':
                return type_annotation.get('name')
            elif type_annotation.get('type') == 'ArrayTypeAnnotation':
                elem_type = type_annotation.get('elementType', {}).get('name', 'number')
                return f"{elem_type}[]"
            elif type_annotation.get('type') == 'TSTypeReference':
                name = type_annotation.get('typeName', {}).get('name', 'any')
                return name
        
        return None
    
    def _extract_param_types(self, func_node: Dict[str, Any]) -> Dict[str, str]:
        """Extract parameter type annotations"""
        param_types = {}
        
        if not isinstance(func_node, dict):
            return param_types
        
        for param in func_node.get('params', []):
            if isinstance(param, dict):
                param_name = param.get('name')
                type_annotation = param.get('typeAnnotation', {})
                
                if type_annotation:
                    type_info = type_annotation.get('typeAnnotation', {})
                    
                    if type_info.get('type') == 'Identifier':
                        param_types[param_name] = type_info.get('name', 'any')
                    elif type_info.get('type') == 'ArrayTypeAnnotation':
                        elem_type = type_info.get('elementType', {}).get('name', 'unknown')
                        param_types[param_name] = f"{elem_type}[]"
                    elif type_info.get('type') == 'TSTypeReference':
                        name = type_info.get('typeName', {}).get('name', 'unknown')
                        param_types[param_name] = name
        
        return param_types
