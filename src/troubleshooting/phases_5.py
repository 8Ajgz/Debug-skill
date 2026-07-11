"""5-phase troubleshooting methodology implementation.

Merged 2026-07-11 against the standalone `troubleshooting` skill's SKILL.md
(6-phase methodology: Resist the Urge to Fix / Classify / Discover Actual
State / Low-Effort First / One Variable at a Time / Sequential Path / Define
Success as Functional). Before this merge, `context` was accepted by
`diagnose()` but never read anywhere in the method body — domain
(code/hardware/general) had no effect on classification or remediation
despite the parameter existing since this module's first version. Fixed by
actually branching on domain, and Phase 0 now flags missing evidence
(SKILL.md Phase 0: "get evidence first") instead of just recording string
length. Anti-pattern list is exposed for callers (e.g. master-debugger) that
want to self-check their own troubleshooting flow against it, not just
consult it as documentation.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

@dataclass
class DiagnosisResult:
    phase_0_evidence: Dict[str, Any] = field(default_factory=dict)
    classified_stage: str = "unknown"  # input/processing/output
    possible_causes: List[str] = field(default_factory=list)
    remediation_steps: List[str] = field(default_factory=list)
    verification_passed: bool = False
    domain: str = "code"

class Troubleshooter:
    """6-phase troubleshooting methodology (Phase 0-4 implemented here as
    diagnose()'s pipeline; Phase 5 "sequential path, not parallel options"
    and Phase 6 "define success as functional" are presentation/interaction
    guidance for the caller, not something a single diagnose() call can
    encode — see ANTI_PATTERNS and the SKILL.md this was merged from for
    the full methodology those phases describe.
    """

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

    # Domain-specific single-most-diagnostic-indicator, from SKILL.md's
    # "Domain Refinements" section. Used by _phase0_gather_evidence to
    # flag when the problem description is missing the one thing that
    # matters most for its domain, rather than just recording length.
    DOMAIN_KEY_EVIDENCE = {
        "code": "the full traceback (not a description of it)",
        "hardware": "whether the problem occurs with only essential components connected",
        "general": "the physical/logical properties of what's broken and where it last worked",
    }

    # SKILL.md's Anti-Patterns table, exposed as data so a caller (e.g.
    # master-debugger orchestrating a troubleshooting pass) can check its
    # own behavior against it, not just read it as documentation.
    ANTI_PATTERNS = [
        ("Proposing solutions before seeing evidence", "Optimizes for the assumed problem, not the real one"),
        ("Assuming standard installation paths", "Misses the actual executable being used"),
        ("Giving parallel options (\"it could be X or Y or Z\")", "Creates decision paralysis"),
        ("Changing multiple things at once", "Makes it impossible to know what worked"),
        ("Stopping at \"status OK\" without checking content", "Silent failures look like successes"),
        ("Repeating the same fix in slightly different forms", "Signals you need to reexamine the assumption, not the fix"),
        ("Treating the visible symptom as the root cause", "The visual failure and the code failure are often in different places"),
    ]

    def diagnose(self, problem: str, context: str = "code") -> DiagnosisResult:
        """Run 5-phase troubleshooting on a problem.

        context: "code" (default), "hardware", or "general" — selects the
        domain refinement branch in Phase 2/3. Unrecognized values fall
        back to "code" rather than silently doing nothing with them.
        """
        domain = context if context in self.DOMAIN_KEY_EVIDENCE else "code"
        result = DiagnosisResult(domain=domain)

        # Phase 0: Get evidence
        result.phase_0_evidence = self._phase0_gather_evidence(problem, domain)
        
        # Phase 1: Classify problem stage
        result.classified_stage = self._phase1_classify(problem)
        
        # Phase 2: Diagnose root causes
        result.possible_causes = self._phase2_diagnose(problem, result.classified_stage, domain)
        
        # Phase 3: Design solutions
        result.remediation_steps = self._phase3_design_solution(
            result.classified_stage,
            result.possible_causes,
            domain,
        )
        
        # Phase 4: Verify solution works
        result.verification_passed = self._phase4_verify(result.remediation_steps)
        
        return result
    
    def _phase0_gather_evidence(self, problem: str, domain: str) -> Dict[str, Any]:
        """Phase 0: Gather evidence from the problem.

        SKILL.md Phase 0 ("Resist the Urge to Fix"): before proposing
        anything, check whether there's actually enough evidence to know
        what's broken. `evidence_sufficient` flags when the domain's single
        most diagnostic indicator (DOMAIN_KEY_EVIDENCE) looks absent from
        the problem description, so a caller can ask for it before
        proceeding to Phase 2/3 instead of guessing.
        """
        has_traceback = "Traceback" in problem
        has_error_message = "Error" in problem or "error" in problem.lower()
        has_command_output = any(
            marker in problem for marker in ("$ ", ">>> ", "Exit code", "stdout", "stderr")
        )
        evidence_sufficient = has_traceback or has_error_message or has_command_output

        return {
            "problem_description": problem,
            "context": domain,
            "length": len(problem),
            "has_traceback": has_traceback,
            "has_error_message": has_error_message,
            "has_command_output": has_command_output,
            "evidence_sufficient": evidence_sufficient,
            "missing_evidence_prompt": (
                None if evidence_sufficient
                else f"Before proposing a fix, get {self.DOMAIN_KEY_EVIDENCE[domain]}."
            ),
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
    
    def _phase2_diagnose(self, problem: str, stage: str, domain: str = "code") -> List[str]:
        """Phase 2: Diagnose root causes"""
        causes = []
        problem_lower = problem.lower()

        if domain == "hardware":
            causes.append("Loose or damaged connection")
            causes.append("Thermal throttling (dust, poor airflow)")
            causes.append("Recent vibration/movement dislodged a component")
            causes.append("Component failure isolated by strip-to-minimum test")
            return causes

        if domain == "general":
            causes.append("Item/state was left at a workflow 'set-down moment' (transition between activities)")
            causes.append("Divergence from expected process occurred earlier than where the failure became visible")
            causes.append("Physical properties of the item (size/weight/shape) determined where it ended up")
            return causes

        # domain == "code" (default) — original stage-based classification,
        # now also checking for AI/ML environment signals per SKILL.md's
        # "Domain Refinements > Code and AI Tooling" section.
        if any(sig in problem_lower for sig in ("cuda", "torch", "conda", "sm_120", "compute capability")):
            causes.append("Package/hardware version mismatch (e.g. CUDA compute capability vs. installed toolkit)")
            causes.append("Conflicting package versions from mixed pip/conda installs")

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
    
    def _phase3_design_solution(self, stage: str, causes: List[str], domain: str = "code") -> List[str]:
        """Phase 3: Design solution based on diagnosis"""
        solutions = []

        if domain == "hardware":
            solutions.append("Strip down to minimum essential components, then add back one at a time")
            solutions.append("Check all connections and reseat any that are loose")
            solutions.append("Clear dust/improve airflow if thermal throttling is suspected")
            solutions.append("Photograph current state before any disassembly")
            return solutions

        if domain == "general":
            solutions.append("Retrace recent activity steps and identify transition/set-down points")
            solutions.append("Search based on the item's physical behavior (falls, hides in gaps, catches in fabric)")
            solutions.append("Work backward from the point of divergence, not just the point of failure")
            return solutions

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

        # Escalation hints, per SKILL.md's "Escalation to specialized skills"
        if stage == "processing" or stage == "unknown":
            solutions.append("If stuck after 3 attempts: escalate to python-debug (execution visibility) or pyprover (formal verification) rather than repeating variations of the same fix")

        return solutions
    
    def _phase4_verify(self, remediation_steps: List[str]) -> bool:
        """
        Phase 4: Heuristic readiness check, not actual solution verification.

        This methodology operates on a text description of a problem, not on
        runnable code, so it cannot execute tests to confirm a fix works. It
        only confirms that Phase 3 produced at least one concrete remediation
        step to act on. Real verification still requires the user (or
        master-debugger's Phase 1 runtime check) to run the suggested fix.
        """
        return len(remediation_steps) > 0
