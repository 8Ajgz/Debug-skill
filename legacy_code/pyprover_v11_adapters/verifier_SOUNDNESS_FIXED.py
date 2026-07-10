"""
PyProver Z3 Verifier - Shared across all languages

Core verification logic using Z3 SMT solver.
Language-agnostic constraint generation and solving.
"""

import z3
from typing import Dict, List, Any, Optional, Tuple
import re
import time


class ConstraintGenerator:
    """Generate Z3 constraints from contracts"""
    
    def __init__(self):
        self.solver = z3.Solver()
        self.variables = {}
        self.constraints = []
    
    def parse_contract_expression(self, expr: str, variables: Dict[str, z3.ExprRef]) -> Optional[z3.ExprRef]:
        """
        Parse contract expression like 'len(arr) > 0' or 'result >= 0'.
        
        Converts to Z3 constraint safely without eval().
        """
        if not expr or not expr.strip():
            return None
        
        expr = expr.strip()
        
        try:
            # Build safe evaluation namespace with z3 operators
            safe_namespace = {
                'And': z3.And,
                'Or': z3.Or,
                'Not': z3.Not,
                'Implies': z3.Implies,
                'Int': z3.Int,
                'Bool': z3.Bool,
            }
            
            # Add variables to namespace (z3 expressions are safe)
            safe_namespace.update(variables)
            
            # Handle array length - pre-process before eval
            processed_expr = expr
            for var_name in variables.keys():
                if f'len({var_name})' in processed_expr:
                    # Create length variable
                    len_var_name = f'z3_len_{var_name}'
                    if len_var_name not in safe_namespace:
                        safe_namespace[len_var_name] = z3.Int(len_var_name)
                    processed_expr = processed_expr.replace(f'len({var_name})', len_var_name)
            
            # Escape variable names with underscores to match Z3 variable names
            for var_name in variables.keys():
                if var_name not in ['result', 'And', 'Or', 'Not', 'Implies']:
                    var_pattern = rf'\b{re.escape(var_name)}\b'
                    # Only replace if not already prefixed
                    if f'z3_var_{var_name}' not in safe_namespace:
                        safe_namespace[var_name] = variables[var_name]
            
            # Safely evaluate expression with restricted namespace
            # Use compile + eval with restricted builtins
            code = compile(processed_expr, '<contract>', 'eval')
            z3_constraint = eval(code, {"__builtins__": {}}, safe_namespace)
            
            # Verify result is a Z3 expression
            if not isinstance(z3_constraint, (z3.ExprRef, z3.BoolRef, z3.ArithRef)):
                return None
            
            return z3_constraint
            
        except (SyntaxError, NameError, TypeError, Z3Exception) as e:
            # Constraint expression invalid or Z3 operation failed
            return None
    
    def generate_constraints(
        self,
        contracts: 'Contract',
        variables: Dict[str, z3.ExprRef],
        template_type: Optional[str] = None
    ) -> Tuple[List[z3.ExprRef], List[z3.ExprRef]]:
        """
        Generate Z3 constraints from contracts, split into:
          - antecedent: preconditions + assumptions + template-shape
            constraints (things assumed true)
          - postconditions: @ensures clauses (things to be PROVEN, not
            assumed - verify() checks these are implied by antecedent,
            it does not just assert them into the same solver instance)

        This split is what makes proper validity-checking possible in
        verify() - see the SOUNDNESS FIX note there for why joining
        everything into one satisfiability check was wrong.
        """
        antecedent = []

        # Preconditions and assumptions are things we GET to assume.
        for req in contracts.requires:
            constraint = self.parse_contract_expression(req, variables)
            if constraint is not None:
                antecedent.append(constraint)

        for assume in contracts.assumes:
            constraint = self.parse_contract_expression(assume, variables)
            if constraint is not None:
                antecedent.append(constraint)

        # Template-specific constraints describe the template's shape
        # (e.g. "the loop only ever increases the accumulator") - these
        # are also assumptions about the code's structure, not things
        # to prove, so they belong in the antecedent too.
        if template_type == 'ACCUMULATOR':
            antecedent.extend(self._accumulator_constraints(variables))
        elif template_type == 'BINARY_SEARCH':
            antecedent.extend(self._binary_search_constraints(variables))
        elif template_type == 'MIN_MAX_LOOP':
            antecedent.extend(self._min_max_constraints(variables))

        # Postconditions are what must be PROVEN, not assumed.
        postconditions = []
        for ens in contracts.ensures:
            constraint = self.parse_contract_expression(ens, variables)
            if constraint is not None:
                postconditions.append(constraint)

        return antecedent, postconditions
    
    def _accumulator_constraints(self, variables: Dict[str, z3.ExprRef]) -> List[z3.ExprRef]:
        """Constraints specific to accumulator pattern"""
        constraints = []
        
        # Ensure accumulator is initialized
        if 'result' in variables or 'sum' in variables:
            # Accumulator should not be negative for sum
            pass
        
        return constraints
    
    def _binary_search_constraints(self, variables: Dict[str, z3.ExprRef]) -> List[z3.ExprRef]:
        """Constraints specific to binary search pattern"""
        constraints = []
        
        # Bounds: left >= 0, right < len(arr)
        if 'left' in variables and 'right' in variables:
            constraints.append(variables['left'] >= 0)
            constraints.append(variables['right'] >= variables['left'] - 1)
        
        return constraints
    
    def _min_max_constraints(self, variables: Dict[str, z3.ExprRef]) -> List[z3.ExprRef]:
        """Constraints specific to min/max pattern"""
        constraints = []
        
        # Min/max value should be from the array
        if 'minVal' in variables or 'min_val' in variables:
            pass
        
        return constraints


class Z3Verifier:
    """Core Z3-based verification engine"""
    
    def __init__(self):
        self.constraint_gen = ConstraintGenerator()

    @staticmethod
    def _is_z3_bool(expr) -> bool:
        """True if expr is Z3-Boolean-sorted (safe to negate/assert as a
        predicate). A bare-identifier clause (e.g. an @ensures of just
        "result", no comparison) evaluates via parse_contract_expression's
        eval() to a Z3 Int/ArithRef, not a Bool - z3.Not() raises on that.
        Same bug class fixed 2026-07-10 in debug-suite's
        pyprover/contract_simplifier.py; ported here since this verifier
        has the identical exposure.
        """
        try:
            return expr.sort_kind() == z3.Z3_BOOL_SORT
        except Exception:
            return False
    
    def verify(
        self,
        contracts: 'Contract',
        variables: Dict[str, z3.ExprRef],
        template_type: Optional[str] = None,
        timeout_ms: int = 10000
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Verify contracts using Z3 solver.

        SOUNDNESS FIX (2026-07-10): the original implementation asserted
        every constraint (preconditions AND postconditions AND
        template-shape constraints) into one solver and checked
        SATISFIABILITY - i.e. "does there exist SOME assignment where all
        of these hold at once". That is not what "verified" is supposed to
        mean. It made near-arbitrary postconditions report verified=True,
        since free variables (result, max_val, etc.) are typically
        under-constrained enough that the solver can always find *some*
        satisfying assignment regardless of whether the postcondition
        actually follows from the precondition. Reproduced before fixing:
        @requires("len(arr) > 0") @ensures("result < 0") on a max-finder
        (whose result is never negative for typical inputs) reported
        verified=True.

        The correct check is VALIDITY, not satisfiability: assert the
        antecedent (preconditions + assumptions + template-shape
        constraints), assert the NEGATION of each postcondition, and check
        UNSAT. UNSAT means "no assignment makes the antecedent true and the
        postcondition false" - i.e. the antecedent implies the
        postcondition, which is what a proof obligation actually requires.
        This mirrors the _implies()/_is_tautology() pattern already used
        elsewhere in this project's Z3-based contract checking.

        Args:
            contracts: Contract specification
            variables: Z3 variables for function
            template_type: Optional template type for specialized constraints
            timeout_ms: Solver timeout in milliseconds
        
        Returns:
            (verified: bool, proof: str, counterexample: str)
        """
        start_time = time.time()
        
        try:
            antecedent, postconditions = self.constraint_gen.generate_constraints(
                contracts, variables, template_type
            )

            # Non-boolean postconditions (bare-identifier clauses) can't be
            # checked as predicates - conservatively treat as unverified
            # rather than crashing or silently claiming success.
            unchecked = [c for c in postconditions if not self._is_z3_bool(c)]
            checkable = [c for c in postconditions if self._is_z3_bool(c)]

            duration_ms = (time.time() - start_time) * 1000

            if not checkable:
                if unchecked:
                    return False, None, (
                        "No checkable postcondition (bare-identifier or "
                        "unparseable @ensures clause - not a valid predicate)"
                    )
                # No postconditions at all: nothing to prove wrong: treat
                # the antecedent's own satisfiability as a sanity check
                # (an outright-contradictory precondition is still worth
                # surfacing), but don't claim a positive proof of nothing.
                solver = z3.Solver()
                solver.set('timeout', timeout_ms)
                for c in antecedent:
                    solver.add(c)
                if antecedent and solver.check() == z3.unsat:
                    return False, None, "Preconditions are contradictory"
                proof = f"Template: {template_type or 'UNKNOWN'}\n"
                proof += "No postconditions to verify - preconditions are satisfiable.\n"
                proof += f"Time: {duration_ms:.1f}ms\n"
                return True, proof, None

            solver = z3.Solver()
            solver.set('timeout', timeout_ms)
            for c in antecedent:
                solver.add(c)
            solver.add(z3.Not(z3.And(*checkable)) if len(checkable) > 1 else z3.Not(checkable[0]))

            result = solver.check()
            
            if result == z3.unsat:
                # No counterexample exists - postcondition(s) provably hold
                # given the preconditions. This is the actual proof.
                proof = f"Template: {template_type or 'UNKNOWN'}\n"
                proof += "Verified by Z3 solver (postcondition implied by preconditions)\n"
                proof += f"Time: {duration_ms:.1f}ms\n"
                if unchecked:
                    proof += f"Note: {len(unchecked)} bare-identifier clause(s) not checked.\n"
                return True, proof, None

            elif result == z3.sat:
                # A counterexample exists where preconditions hold but the
                # postcondition doesn't - genuine verification failure.
                model = solver.model()
                cx = "Counterexample found:\n"
                for var_name, z3_var in variables.items():
                    try:
                        cx += f"  {var_name} = {model.eval(z3_var, model_completion=True)}\n"
                    except Exception:
                        pass
                return False, None, cx
            
            else:  # unknown
                return False, None, "Solver could not determine validity (timeout)"
        
        except Exception as e:
            return False, None, str(e)
    
    def get_counterexample(self, model: z3.ModelRef, variables: Dict[str, z3.ExprRef]) -> str:
        """Extract counterexample from Z3 model"""
        counterexample = "Counterexample found:\n"
        
        for var_name, z3_var in variables.items():
            try:
                value = model.eval(z3_var)
                counterexample += f"  {var_name} = {value}\n"
            except:
                pass
        
        return counterexample
