"""Loop invariant templates for common algorithm shapes.

Ported from the v8.2 core (roadmap sections 2.1 and 13.3). Each template turns
variable names into an invariant string for a loop. Strings are suggestions.
The Z3 verifier does not check them, because it does not model subscripts,
len() or sum(). Tests check each invariant against a reference loop at every
iteration instead.

Not ported, and why:
- RECURSION: its "base OR inductive step" form is weaker than any real
  invariant, so it would accept wrong code.
- WHILE_LOOP: its bound is a fixed guess (100 when the length is unknown), not
  an invariant.
- ACCUMULATOR with op_type "product": there is no product() builtin, so the
  string would not evaluate. Only "sum" is supported.
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class BinarySearchBounds:
    """Bounds maintained by a binary search over arr_var (lo and hi inclusive)."""
    arr_var: str = "arr"
    lo_var: str = "lo"
    hi_var: str = "hi"

    def generate_invariant(self) -> str:
        return (f"{self.lo_var} >= 0 and {self.hi_var} < len({self.arr_var}) "
                f"and {self.lo_var} <= {self.hi_var} + 1")


@dataclass(frozen=True)
class MinMaxLoop:
    """best_var holds the min or max of the prefix processed so far."""
    best_var: str
    op: str = "min"          # "min" or "max"
    arr_var: str = "arr"
    index_var: str = "i"

    def generate_invariant(self) -> str:
        if self.op not in ("min", "max"):
            raise ValueError(f"op must be 'min' or 'max', not {self.op!r}")
        return f"{self.best_var} == {self.op}({self.arr_var}[:{self.index_var}+1])"


@dataclass(frozen=True)
class SumAccumulator:
    """acc_var holds the sum of the elements processed before the current index."""
    acc_var: str
    arr_var: str = "arr"
    index_var: str = "i"

    def generate_invariant(self) -> str:
        return f"{self.acc_var} == sum({self.arr_var}[:{self.index_var}])"


@dataclass(frozen=True)
class FilterCount:
    """count_var counts the elements of the prefix that satisfy condition (written in x)."""
    count_var: str
    condition: str
    arr_var: str = "arr"
    index_var: str = "i"

    def generate_invariant(self) -> str:
        return (f"{self.count_var} == len([x for x in {self.arr_var}[:{self.index_var}] "
                f"if {self.condition}])")


@dataclass(frozen=True)
class Scan:
    """output_var has one entry per processed index (running-result loops)."""
    output_var: str = "result"
    index_var: str = "i"

    def generate_invariant(self) -> str:
        return f"len({self.output_var}) == {self.index_var}"


@dataclass(frozen=True)
class StateMachine:
    """state_var always holds one of the declared states."""
    states: Tuple[str, ...]
    state_var: str = "state"

    def generate_invariant(self) -> str:
        if not self.states:
            raise ValueError("a state machine needs at least one state")
        return "(" + " or ".join(f'{self.state_var} == "{s}"' for s in self.states) + ")"
