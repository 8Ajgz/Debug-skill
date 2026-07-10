"""
PyProver NASM Adapter

Implements LanguageAdapter for NASM (Netwide Assembler) x86/x86-64 assembly.
Parses NASM source code, extracts contracts from comments,
detects patterns, and integrates with Z3 verification backend.

Supports:
- x86-64 (64-bit) and x86 (32-bit) instruction sets
- Contract annotations in comments (;; @requires/@ensures)
- Memory operations (mov, lea)
- Arithmetic operations (add, sub, mul, div)
- Control flow (jmp, je, jne, loop, ret)
- Register state tracking
- Loop invariant detection
"""

import re
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass
from ..interfaces import LanguageAdapter, Contract


@dataclass
class AssemblyInstruction:
    """Represents a single assembly instruction"""
    mnemonic: str
    operands: List[str]
    line_number: int
    raw: str
    comment: Optional[str] = None


class NAsmAdapter(LanguageAdapter):
    """Adapter for NASM x86/x86-64 assembly verification"""
    
    # Register names by size
    REGISTERS_64 = {'rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp',
                    'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15'}
    REGISTERS_32 = {'eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp',
                    'r8d', 'r9d', 'r10d', 'r11d', 'r12d', 'r13d', 'r14d', 'r15d'}
    REGISTERS_16 = {'ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp',
                    'r8w', 'r9w', 'r10w', 'r11w', 'r12w', 'r13w', 'r14w', 'r15w'}
    REGISTERS_8 = {'al', 'ah', 'bl', 'bh', 'cl', 'ch', 'dl', 'dh',
                   'r8b', 'r9b', 'r10b', 'r11b', 'r12b', 'r13b', 'r14b', 'r15b'}
    
    ALL_REGISTERS = REGISTERS_64 | REGISTERS_32 | REGISTERS_16 | REGISTERS_8
    
    @property
    def language_name(self) -> str:
        return 'nasm'
    
    def parse_function(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """
        Parse NASM source code and extract function.
        
        Args:
            source_code: NASM assembly source code
            func_name: Name of function/label to extract
        
        Returns:
            Dictionary with 'ast', 'source', 'language', and 'instructions' keys
        
        Raises:
            SyntaxError: If code cannot be parsed
            ValueError: If function not found
        """
        lines = source_code.split('\n')
        
        # Find function start
        func_start = None
        for i, line in enumerate(lines):
            # Look for label matching function name
            if self._is_label(line, func_name):
                func_start = i
                break
        
        if func_start is None:
            raise ValueError(f"Function '{func_name}' not found in NASM code")
        
        # Extract function body (until next label or EOF)
        func_end = len(lines)
        for i in range(func_start + 1, len(lines)):
            if self._is_label_definition(lines[i]):
                func_end = i
                break
        
        # Parse instructions
        instructions = []
        for i in range(func_start, func_end):
            instr = self._parse_instruction(lines[i], i)
            if instr:
                instructions.append(instr)
        
        return {
            'ast': instructions,
            'source': source_code,
            'language': 'nasm',
            'function_name': func_name,
            'instructions': instructions
        }
    
    def extract_contracts(self, ast_data: Dict[str, Any]) -> Contract:
        """
        Extract contracts from NASM code annotations.
        
        Looks for comments with:
        - ;; @requires constraint
        - ;; @ensures constraint
        - ;; @assume fact
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            Contract object with extracted constraints
        """
        source = ast_data.get('source', '')
        requires = []
        ensures = []
        assumes = []
        
        # Extract contract comments
        comment_pattern = r';\s*@(requires|ensures|assume)\s+([^;]*?)(?:;|$)'
        for match in re.finditer(comment_pattern, source):
            directive = match.group(1)
            constraint = match.group(2).strip()
            
            if directive == 'requires':
                requires.append(constraint)
            elif directive == 'ensures':
                ensures.append(constraint)
            elif directive == 'assume':
                assumes.append(constraint)
        
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
        Extract all variables (registers, memory locations) from NASM function.
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            List of variable names (registers and named memory locations)
        """
        instructions = ast_data.get('instructions', [])
        variables = set()
        
        for instr in instructions:
            # Extract registers from operands
            for operand in instr.operands:
                operand_clean = operand.strip().lower()
                
                # Check if it's a register
                if operand_clean in self.ALL_REGISTERS:
                    variables.add(operand_clean)
                
                # Check for named memory location (label)
                if re.match(r'^\[?[a-zA-Z_]\w*\]?$', operand_clean):
                    variables.add(operand_clean)
        
        return sorted(list(variables))
    
    def extract_loops(self, ast_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract loop patterns from NASM function.
        
        Detects:
        - loop instruction
        - jmp backward (branch to earlier label)
        - call to same function (recursion)
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            List of loop specifications
        """
        instructions = ast_data.get('instructions', [])
        source = ast_data.get('source', '')
        loops = []
        
        # Find loop instructions
        for i, instr in enumerate(instructions):
            if instr.mnemonic == 'loop':
                loops.append({
                    'type': 'loop',
                    'target': instr.operands[0] if instr.operands else None,
                    'line': instr.line_number,
                    'is_loop': True
                })
            
            # Find backward jumps (loops)
            elif instr.mnemonic in ['jmp', 'je', 'jne', 'jz', 'jnz', 'jg', 'jl']:
                target = instr.operands[0] if instr.operands else None
                if target:
                    loops.append({
                        'type': 'jump',
                        'mnemonic': instr.mnemonic,
                        'target': target,
                        'line': instr.line_number,
                        'is_loop_like': True
                    })
            
            # Find call instructions
            elif instr.mnemonic == 'call':
                target = instr.operands[0] if instr.operands else None
                if target == ast_data.get('function_name'):
                    loops.append({
                        'type': 'recursion',
                        'target': target,
                        'is_recursive': True,
                        'line': instr.line_number
                    })
        
        return loops
    
    def infer_template(self, ast_data: Dict[str, Any]) -> Optional[str]:
        """
        Detect verification template from NASM code patterns.
        
        Recognizes:
        - ACCUMULATOR: add/sub in loop
        - MIN_MAX_LOOP: cmp + conditional jumps
        - RECURSION: call to self
        - STATE_MACHINE: multiple conditional branches
        - BINARY_SEARCH: division/shift operations with jumps
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            Template type string or None
        """
        instructions = ast_data.get('instructions', [])
        loops = self.extract_loops(ast_data)
        
        if not loops:
            return None
        
        # Collect mnemonics
        mnemonics = set(instr.mnemonic for instr in instructions)
        
        # Check for ACCUMULATOR: add/sub/inc in loops
        if any(m in ['add', 'sub', 'inc', 'dec'] for m in mnemonics):
            if any('add' in str(instr.raw) for instr in instructions):
                return 'ACCUMULATOR'
        
        # Check for RECURSION: call to self
        if any(loop.get('is_recursive') for loop in loops):
            return 'RECURSION'
        
        # Check for STATE_MACHINE: multiple conditional jumps
        conditional_jumps = sum(1 for instr in instructions 
                               if instr.mnemonic in ['je', 'jne', 'jz', 'jnz', 'jg', 'jl'])
        if conditional_jumps >= 2:
            return 'STATE_MACHINE'
        
        # Check for BINARY_SEARCH: shift or division with jumps
        if 'shr' in mnemonics or 'shl' in mnemonics or 'div' in mnemonics:
            if any(instr.mnemonic in ['jmp', 'je', 'jne'] for instr in instructions):
                return 'BINARY_SEARCH'
        
        # Check for MIN_MAX_LOOP: cmp + conditional jump
        if 'cmp' in mnemonics and any(instr.mnemonic in ['jg', 'jl', 'jge', 'jle'] 
                                     for instr in instructions):
            return 'MIN_MAX_LOOP'
        
        # Default to generic pattern
        return 'SCAN' if loops else None
    
    # ===== Internal Parsing Methods =====
    
    def _parse_instruction(self, line: str, line_num: int) -> Optional[AssemblyInstruction]:
        """Parse single NASM instruction line."""
        # Remove comments
        if ';' in line:
            code_part, comment = line.split(';', 1)
            comment = comment.strip()
        else:
            code_part = line
            comment = None
        
        code_part = code_part.strip()
        
        # Skip empty lines and labels
        if not code_part or code_part.endswith(':'):
            return None
        
        # Parse instruction
        parts = code_part.split(None, 1)
        if not parts:
            return None
        
        mnemonic = parts[0].lower()
        operands_str = parts[1] if len(parts) > 1 else ""
        
        # Parse operands
        operands = [op.strip() for op in operands_str.split(',')]
        operands = [op for op in operands if op]
        
        return AssemblyInstruction(
            mnemonic=mnemonic,
            operands=operands,
            line_number=line_num,
            raw=code_part,
            comment=comment
        )
    
    def _is_label(self, line: str, label_name: str) -> bool:
        """Check if line is a label definition matching the name."""
        line = line.strip()
        pattern = rf'^{re.escape(label_name)}\s*:'
        return bool(re.match(pattern, line, re.IGNORECASE))
    
    def _is_label_definition(self, line: str) -> bool:
        """Check if line is any label definition."""
        line = line.strip()
        return bool(re.match(r'^[a-zA-Z_]\w*\s*:', line))
    
    def _extract_state_tracking(self, ast_data: Dict[str, Any]) -> Dict[str, str]:
        """Extract state tracking annotations from comments."""
        source = ast_data.get('source', '')
        state_tracking = {}
        
        # Look for @state_tracking annotations
        state_pattern = r';\s*@state_tracking\s+(\w+)\s*=\s*([^;]+)'
        for match in re.finditer(state_pattern, source):
            var_name = match.group(1)
            state_expr = match.group(2).strip()
            state_tracking[var_name] = state_expr
        
        return state_tracking
