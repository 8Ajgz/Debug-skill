"""
PyProver WebAssembly Adapter

Implements LanguageAdapter for WebAssembly (WASM).
Parses WASM modules (WAT/binary), extracts contracts from memory annotations,
detects patterns, and integrates with Z3 verification backend.

Supports:
- WebAssembly Text (WAT) format
- WASM module metadata and annotations
- Memory, table, and function contract specifications
- Type-safe constraint generation for WASM operations
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from ..interfaces import LanguageAdapter, Contract


@dataclass
class WASTNode:
    """Represents a WAT S-expression node"""
    type: str
    value: Optional[str] = None
    children: List['WASTNode'] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []


class WebAssemblyAdapter(LanguageAdapter):
    """Adapter for WebAssembly code verification"""
    
    @property
    def language_name(self) -> str:
        return 'webassembly'
    
    def parse_function(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """
        Parse WASM module and extract function.
        
        Supports both WebAssembly Text (WAT) format and inline WASM annotations.
        
        Args:
            source_code: WAT module or WASM annotation format
            func_name: Name of function to extract
        
        Returns:
            Dictionary with 'ast', 'source', 'language', and 'wasm_type' keys
        
        Raises:
            SyntaxError: If WASM module is invalid
            ValueError: If function not found
        """
        source_code = source_code.strip()
        
        # Detect input format
        is_wat = source_code.startswith('(module') or source_code.startswith('(func')
        
        if is_wat:
            # Parse WAT format
            ast = self._parse_wat(source_code)
        else:
            # Try to parse as annotated WASM format
            ast = self._parse_annotated_wasm(source_code)
        
        if ast is None:
            raise SyntaxError("Invalid WebAssembly syntax")
        
        # Extract specific function
        func_node = self._find_function(ast, func_name)
        if func_node is None:
            raise ValueError(f"Function '{func_name}' not found in WASM module")
        
        return {
            'ast': func_node,
            'module_ast': ast,
            'source': source_code,
            'language': 'webassembly',
            'wasm_type': 'wat' if is_wat else 'annotated'
        }
    
    def extract_contracts(self, ast_data: Dict[str, Any]) -> Contract:
        """
        Extract contracts from WASM function annotations.
        
        Looks for WASM contract annotations in comments:
        - (;; @requires constraint ;)
        - (;; @ensures constraint ;)
        - (;; @assume fact ;)
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            Contract object with extracted constraints
        """
        func_node = ast_data.get('ast')
        source = ast_data.get('source', '')
        
        requires = []
        ensures = []
        assumes = []
        
        # Extract comments before/in function
        comment_pattern = r'\(\;;\s*@(requires|ensures|assume)\s+([^;]+)\;'
        for match in re.finditer(comment_pattern, source):
            directive = match.group(1)
            constraint = match.group(2).strip()
            
            if directive == 'requires':
                requires.append(constraint)
            elif directive == 'ensures':
                ensures.append(constraint)
            elif directive == 'assume':
                assumes.append(constraint)
        
        # Extract from function metadata if available
        if func_node and hasattr(func_node, 'children'):
            for child in func_node.children:
                if hasattr(child, 'value') and child.value and 'contract' in child.value:
                    # Parse structured contract metadata
                    contract_meta = self._parse_contract_metadata(child.value)
                    requires.extend(contract_meta.get('requires', []))
                    ensures.extend(contract_meta.get('ensures', []))
                    assumes.extend(contract_meta.get('assume', []))
        
        # Infer template type
        template_type = self.infer_template(ast_data)
        
        return Contract(
            requires=requires or ["true"],
            ensures=ensures or ["true"],
            assumes=assumes,
            template_type=template_type,
            state_tracking=self._extract_state_tracking(ast_data)
        )
    
    def extract_variables(self, ast_data: Dict[str, Any]) -> List[str]:
        """
        Extract all variables (locals, parameters, globals) from WASM function.
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            List of variable names
        """
        func_node = ast_data.get('ast')
        variables = set()
        
        if not func_node:
            return []
        
        # Extract function parameters
        param_pattern = r'\(param\s+(\$?\w+)\s+\w+\)'
        for match in re.finditer(param_pattern, ast_data.get('source', '')):
            variables.add(match.group(1))
        
        # Extract local variables
        local_pattern = r'\(local\s+(\$?\w+)\s+\w+\)'
        for match in re.finditer(local_pattern, ast_data.get('source', '')):
            variables.add(match.group(1))
        
        # Extract global references
        global_pattern = r'\(global\.\w+\s+(\$?\w+)\)'
        for match in re.finditer(global_pattern, ast_data.get('source', '')):
            variables.add(match.group(1))
        
        # Extract memory/table references
        memory_pattern = r'\(memory\s+(\$?\w+)'
        for match in re.finditer(memory_pattern, ast_data.get('source', '')):
            variables.add(match.group(1))
        
        return sorted(list(variables))
    
    def extract_loops(self, ast_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract loop patterns from WASM function.
        
        Detects:
        - block/loop/br patterns
        - Recursive calls
        - br_table structures
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            List of loop node specifications
        """
        source = ast_data.get('source', '')
        loops = []
        
        # Detect block/loop structures
        loop_pattern = r'\(loop\s+(\$\w+)\s*(.*?)\)'
        for match in re.finditer(loop_pattern, source, re.DOTALL):
            loop_label = match.group(1)
            loop_body = match.group(2)
            
            loops.append({
                'type': 'loop',
                'label': loop_label,
                'body': loop_body,
                'has_br': 'br' in loop_body
            })
        
        # Detect block structures with branches
        block_pattern = r'\(block\s+(\$\w+)\s*(.*?)\(br\s+\d+\)\)'
        for match in re.finditer(block_pattern, source, re.DOTALL):
            block_label = match.group(1)
            block_body = match.group(2)
            
            loops.append({
                'type': 'block',
                'label': block_label,
                'body': block_body,
                'is_loop_like': True
            })
        
        # Detect recursion patterns
        func_name = self._extract_function_name(ast_data)
        if func_name:
            recurse_pattern = r'\(call\s+\$?' + re.escape(func_name) + r'\)'
            if re.search(recurse_pattern, source):
                loops.append({
                    'type': 'recursion',
                    'target': func_name,
                    'is_recursive': True
                })
        
        return loops
    
    def infer_template(self, ast_data: Dict[str, Any]) -> Optional[str]:
        """
        Detect verification template from WASM code patterns.
        
        Recognizes:
        - ACCUMULATOR: memory.store in loop
        - BINARY_SEARCH: conditional branches with halving
        - RECURSION: call to self
        - STATE_MACHINE: br_table with multiple targets
        - MIN_MAX_LOOP: comparison operations in loop
        - FILTER: conditional memory.store
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            Template type string or None
        """
        source = ast_data.get('source', '')
        loops = self.extract_loops(ast_data)
        
        if not loops:
            return None
        
        # Check for ACCUMULATOR pattern: memory.store in loop
        if any('memory.store' in loop.get('body', '') for loop in loops):
            return 'ACCUMULATOR'
        
        # Check for RECURSION pattern
        if any(loop.get('is_recursive') for loop in loops):
            return 'RECURSION'
        
        # Check for STATE_MACHINE pattern: br_table
        if 'br_table' in source:
            return 'STATE_MACHINE'
        
        # Check for BINARY_SEARCH: i32.shr_u or halving operation
        if any('i32.shr_u' in loop.get('body', '') or 'i32.div_u' in loop.get('body', '')
               for loop in loops):
            return 'BINARY_SEARCH'
        
        # Check for MIN_MAX_LOOP: i32.gt_u or i32.lt_u
        if any('i32.gt_u' in loop.get('body', '') or 'i32.lt_u' in loop.get('body', '')
               for loop in loops):
            return 'MIN_MAX_LOOP'
        
        # Check for FILTER: conditional with local.get/set
        if any('if' in loop.get('body', '') and 'local.set' in loop.get('body', '')
               for loop in loops):
            return 'FILTER'
        
        # Default to generic pattern
        return None if not loops else 'SCAN'
    
    # ===== Internal Parsing Methods =====
    
    def _parse_wat(self, source: str) -> Optional[WASTNode]:
        """Parse WebAssembly Text (WAT) format into S-expression tree."""
        try:
            return self._parse_sexpr(source.strip())
        except Exception:
            return None
    
    def _parse_sexpr(self, text: str, pos: int = 0) -> Tuple[Optional[WASTNode], int]:
        """
        Parse S-expression from text starting at position pos.
        Returns (parsed_node, next_position).
        """
        # Skip whitespace and comments
        while pos < len(text) and text[pos] in ' \t\n\r':
            pos += 1
        
        if pos >= len(text):
            return None, pos
        
        # Handle block comments
        if text[pos:pos+2] == '(;':
            end = text.find(';)', pos)
            if end != -1:
                return self._parse_sexpr(text, end + 2)
            return None, len(text)
        
        # Parse S-expression
        if text[pos] == '(':
            pos += 1
            node = WASTNode(type='list', children=[])
            
            # Parse first element (operator/keyword)
            token, pos = self._read_token(text, pos)
            if token:
                node.type = token
            
            # Parse remaining elements
            while pos < len(text) and text[pos] != ')':
                child, pos = self._parse_sexpr(text, pos)
                if child:
                    node.children.append(child)
            
            if pos < len(text) and text[pos] == ')':
                pos += 1
            
            return node, pos
        
        # Parse atom (number, identifier, string)
        token, pos = self._read_token(text, pos)
        if token:
            return WASTNode(type='atom', value=token), pos
        
        return None, pos
    
    def _read_token(self, text: str, pos: int) -> Tuple[Optional[str], int]:
        """Read next token from WAT text."""
        # Skip whitespace
        while pos < len(text) and text[pos] in ' \t\n\r':
            pos += 1
        
        if pos >= len(text):
            return None, pos
        
        start = pos
        
        # Read token (alphanumeric, underscore, dollar sign, dot, etc.)
        while pos < len(text) and text[pos] not in ' \t\n\r()':
            pos += 1
        
        if pos > start:
            return text[start:pos], pos
        
        return None, pos
    
    def _parse_annotated_wasm(self, source: str) -> Optional[WASTNode]:
        """Parse WASM annotation format (comments with @requires/@ensures)."""
        # Try to parse as extended format with WASM annotations
        lines = source.split('\n')
        
        root = WASTNode(type='module', children=[])
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith(';;'):
                continue
            
            # Try to find function-like declarations
            if 'func' in line or 'export' in line:
                node = WASTNode(type='declaration', value=line)
                root.children.append(node)
        
        return root if root.children else None
    
    def _find_function(self, module: WASTNode, func_name: str) -> Optional[WASTNode]:
        """Find function node in WAT module."""
        if not module or not hasattr(module, 'children'):
            return None
        
        # Search for function in module
        for child in module.children:
            if hasattr(child, 'type') and child.type == 'func':
                # Check if function name matches
                if hasattr(child, 'value') and func_name in child.value:
                    return child
                
                # Check in children for name
                if hasattr(child, 'children'):
                    for grandchild in child.children:
                        if hasattr(grandchild, 'value') and func_name in grandchild.value:
                            return child
            
            # Recursively search in nested lists
            elif hasattr(child, 'type') and child.type == 'list':
                result = self._find_function(child, func_name)
                if result:
                    return result
        
        return None
    
    def _extract_function_name(self, ast_data: Dict[str, Any]) -> Optional[str]:
        """Extract function name from AST."""
        func_node = ast_data.get('ast')
        source = ast_data.get('source', '')
        
        # Try to extract from function declaration
        func_pattern = r'\(func\s+(\$?\w+)'
        match = re.search(func_pattern, source)
        if match:
            return match.group(1)
        
        return None
    
    def _extract_state_tracking(self, ast_data: Dict[str, Any]) -> Dict[str, str]:
        """Extract state tracking annotations."""
        source = ast_data.get('source', '')
        state_tracking = {}
        
        # Look for @state_tracking annotations
        state_pattern = r'\(\;\;\s*@state_tracking\s+(\$\w+)\s*=\s*([^;]+)\;'
        for match in re.finditer(state_pattern, source):
            var_name = match.group(1)
            state_expr = match.group(2).strip()
            state_tracking[var_name] = state_expr
        
        return state_tracking
    
    def _parse_contract_metadata(self, metadata_str: str) -> Dict[str, List[str]]:
        """Parse structured contract metadata from string."""
        contracts = {'requires': [], 'ensures': [], 'assume': []}
        
        # Parse contract: notation
        contract_pattern = r'(\w+):\s*([^,\}]+)'
        for match in re.finditer(contract_pattern, metadata_str):
            key = match.group(1)
            value = match.group(2).strip()
            
            if key in contracts:
                contracts[key].append(value)
        
        return contracts
