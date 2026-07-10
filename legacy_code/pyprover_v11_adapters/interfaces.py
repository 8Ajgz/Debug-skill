"""
PyProver v11.1 - Language Adapter Interfaces

Defines the contract that all language adapters must implement.
Enables Python, JavaScript, TypeScript, Rust, C Safe Subset, C++20, WebAssembly, 
NASM, and FASM support through a unified interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class TemplateType(Enum):
    """Verification template types"""
    ACCUMULATOR = "ACCUMULATOR"
    BINARY_SEARCH = "BINARY_SEARCH"
    RECURSION = "RECURSION"
    STATE_MACHINE = "STATE_MACHINE"
    MIN_MAX_LOOP = "MIN_MAX_LOOP"
    FILTER = "FILTER"
    SCAN = "SCAN"
    SORTED_ARRAY = "SORTED_ARRAY"
    PARTITION = "PARTITION"
    PERMUTATION = "PERMUTATION"


@dataclass
class Contract:
    """Language-agnostic contract representation"""
    requires: List[str]
    ensures: List[str]
    assumes: List[str]
    template_type: Optional[str] = None
    state_tracking: Dict[str, str] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Unified verification result across all languages"""
    verified: bool
    function_name: str
    language: str
    template_type: Optional[str] = None
    proof: Optional[str] = None
    counterexample: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'verified': self.verified,
            'function_name': self.function_name,
            'language': self.language,
            'template_type': self.template_type,
            'proof': self.proof,
            'counterexample': self.counterexample,
            'error': self.error,
            'duration_ms': self.duration_ms
        }


class LanguageAdapter(ABC):
    """
    Abstract base class for language-specific adapters.
    
    Each language (Python, JavaScript, TypeScript) implements this interface
    to provide language-specific parsing, contract extraction, and type mapping.
    """
    
    @property
    @abstractmethod
    def language_name(self) -> str:
        """Return the language name (e.g., 'python', 'javascript', 'typescript')"""
        pass
    
    @abstractmethod
    def parse_function(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """
        Parse function and extract AST.
        
        Args:
            source_code: Source code containing the function
            func_name: Name of function to extract
        
        Returns:
            Dictionary with 'ast', 'source', and 'language' keys
        
        Raises:
            SyntaxError: If code cannot be parsed
            ValueError: If function not found
        """
        pass
    
    @abstractmethod
    def extract_contracts(self, ast_data: Dict[str, Any]) -> Contract:
        """
        Extract contracts (@requires, @ensures, @assume) from AST.
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            Contract object with requirements and guarantees
        """
        pass
    
    @abstractmethod
    def extract_variables(self, ast_data: Dict[str, Any]) -> List[str]:
        """
        Get all variables used in function.
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            List of variable names
        """
        pass
    
    @abstractmethod
    def extract_loops(self, ast_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find loop patterns in function.
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            List of loop nodes with type, test, body, etc.
        """
        pass
    
    @abstractmethod
    def infer_template(self, ast_data: Dict[str, Any]) -> Optional[str]:
        """
        Detect verification template type from code patterns.
        
        Args:
            ast_data: Result from parse_function()
        
        Returns:
            Template type string or None if no pattern matches
        """
        pass
    
    @abstractmethod
    def map_type_to_z3(self, type_hint: str) -> Any:
        """
        Map language type to Z3 sort.
        
        Args:
            type_hint: Type string from language (e.g., 'int', 'number', 'string')
        
        Returns:
            Z3 Sort object
        """
        pass
    
    def get_function_metadata(self, ast_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract function metadata (name, params, return type, etc.).
        
        Default implementation; override in subclass for richer metadata.
        """
        return {
            'language': self.language_name,
            'variables': self.extract_variables(ast_data),
            'loops': len(self.extract_loops(ast_data))
        }
