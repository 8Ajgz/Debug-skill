"""5-phase troubleshooting methodology implementation"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

@dataclass
class DiagnosisResult:
    phase_0_evidence: Dict[str, Any] = field(default_factory=dict)
    classified_stage: str = "unknown"  # input/processing/output
    possible_causes: List[str] = field(default_factory=list)
    remediation_steps: List[str] = field(default_factory=list)
    verification_passed: bool = False

class Troubleshooter:
    """5-phase troubleshooting methodology"""
    
    # Problem classification patterns
    INPUT_PATTERNS = {
        'module': 'ModuleNotFoundError',
        'import': 'ImportError',
        'not found': 'FileNotFoundError',
        'no such': 'FileNotFoundError',
    }
    
    PROCESSING_PATTERNS = {
        'type error': 'TypeError',
        'value error': 'ValueError',
        'key error': 'KeyError',
        'attribute': 'AttributeError',
        'index': 'IndexError',
        'zero': 'ZeroDivisionError',
    }
    
    OUTPUT_PATTERNS = {
        'wrong': 'IncorrectOutput',
        'unexpected': 'UnexpectedOutput',
        'null': 'NullOutput',
        'empty': 'EmptyOutput',
    }
    
    def diagnose(self, problem: str, context: str = "code") -> DiagnosisResult:
        """Run 5-phase troubleshooting on a problem"""
        result = DiagnosisResult()
        
        # Phase 0: Get evidence
        result.phase_0_evidence = self._phase0_gather_evidence(problem, context)
        
        # Phase 1: Classify problem stage
        result.classified_stage = self._phase1_classify(problem)
        
        # Phase 2: Diagnose root causes
        result.possible_causes = self._phase2_diagnose(problem, result.classified_stage)
        
        # Phase 3: Design solutions
        result.remediation_steps = self._phase3_design_solution(
            result.classified_stage,
            result.possible_causes
        )
        
        # Phase 4: Verify solution works
        result.verification_passed = self._phase4_verify(result.remediation_steps)
        
        return result
    
    def _phase0_gather_evidence(self, problem: str, context: str) -> Dict[str, Any]:
        """Phase 0: Gather evidence from the problem"""
        return {
            "problem_description": problem,
            "context": context,
            "length": len(problem),
            "has_traceback": "Traceback" in problem,
            "has_error_message": "Error" in problem or "error" in problem.lower(),
        }
    
    def _phase1_classify(self, problem: str) -> str:
        """Phase 1: Classify the problem (input/processing/output)"""
        problem_lower = problem.lower()
        
        # Check INPUT stage patterns
        for pattern in self.INPUT_PATTERNS.keys():
            if pattern in problem_lower:
                return "input"
        
        # Check PROCESSING stage patterns
        for pattern in self.PROCESSING_PATTERNS.keys():
            if pattern in problem_lower:
                return "processing"
        
        # Check OUTPUT stage patterns
        for pattern in self.OUTPUT_PATTERNS.keys():
            if pattern in problem_lower:
                return "output"
        
        return "unknown"
    
    def _phase2_diagnose(self, problem: str, stage: str) -> List[str]:
        """Phase 2: Diagnose root causes"""
        causes = []
        problem_lower = problem.lower()
        
        if stage == "input":
            if "module" in problem_lower:
                causes.append("Module not installed")
                causes.append("Wrong Python environment")
                causes.append("Typo in module name")
            elif "file" in problem_lower:
                causes.append("File path is incorrect")
                causes.append("File doesn't exist")
                causes.append("Permission denied")
        
        elif stage == "processing":
            if "type" in problem_lower:
                causes.append("Mismatched data types")
                causes.append("Type conversion needed")
                causes.append("None value where not expected")
            elif "key" in problem_lower or "attribute" in problem_lower:
                causes.append("Missing dictionary key")
                causes.append("Missing object attribute")
                causes.append("Typo in attribute/key name")
            elif "zero" in problem_lower:
                causes.append("Division by zero")
                causes.append("Zero not validated before use")
        
        elif stage == "output":
            causes.append("Logic error in computation")
            causes.append("Missing data transformation")
            causes.append("Incorrect initial values")
        
        return causes if causes else ["Unknown cause - more investigation needed"]
    
    def _phase3_design_solution(self, stage: str, causes: List[str]) -> List[str]:
        """Phase 3: Design solution based on diagnosis"""
        solutions = []
        
        if stage == "input":
            solutions.append("Check file path and verify file exists")
            solutions.append("Verify correct Python environment is active")
            solutions.append("Install missing packages: pip install <package>")
            solutions.append("Check spelling of module/file names")
        
        elif stage == "processing":
            solutions.append("Add type hints to verify types at runtime")
            solutions.append("Add None checks before using variables")
            solutions.append("Use type conversion functions (int(), str(), etc.)")
            solutions.append("Add defensive programming checks")
        
        elif stage == "output":
            solutions.append("Add logging to trace computations")
            solutions.append("Check initial values and assumptions")
            solutions.append("Verify data flows through pipeline correctly")
        
        else:
            solutions.append("Enable debug mode and trace execution")
            solutions.append("Add print statements to isolate issue")
            solutions.append("Break problem into smaller test cases")
        
        return solutions
    
    def _phase4_verify(self, remediation_steps: List[str]) -> bool:
        """Phase 4: Verify solution works (placeholder)"""
        # In practice, would run tests here
        return len(remediation_steps) > 0
