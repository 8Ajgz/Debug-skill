#!/usr/bin/env python3
"""
bug_patterns: Recognize common bug patterns from a DebugReport.

Detects:
  - Off-by-one loop errors
  - Missing null/key checks
  - Aliasing mutations
  - Type confusion
  - Division by zero
  - Resource leaks
  - Mutating during iteration

Works with the DebugReport produced by debug_report.execute_with_debug.

Usage:
    from debug_report import execute_with_debug
    from bug_patterns import BugPatternDetector

    code = '''
    arr = [1, 2, 3]
    for i in range(1, len(arr)+1):
        x = arr[i]
    '''
    report = execute_with_debug(code)
    detector = BugPatternDetector(report)
    patterns = detector.analyze()

    print(detector.generate_combined_report())
    for p in patterns:
        print(p.generate_report())
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class BugPatternType(Enum):
    """Types of bugs detected."""
    OFF_BY_ONE = "off_by_one_loop"
    NULL_CHECK = "missing_null_check"
    ALIASING = "aliasing_mutation"
    TYPE_CONFUSION = "type_mismatch"
    DIVISION_BY_ZERO = "division_by_zero"
    RESOURCE_LEAK = "resource_not_cleaned"
    RESOURCE_LEAK_ON_EXCEPTION = "resource_leak_on_exception"
    MUTATING_ITERATOR = "mutating_during_iteration"
    FLOATING_POINT = "floating_point_precision"
    INFINITE_LOOP = "infinite_loop"
    STACK_OVERFLOW = "recursion_limit"
    SILENT_EXCEPTION = "silent_exception_swallow"
    UNHANDLED_EXCEPTION = "unhandled_exception"


@dataclass
class DetectedPattern:
    """A detected bug pattern with actionable suggestion."""
    pattern_type: BugPatternType
    severity: str          # "low" | "medium" | "high" | "critical"
    confidence: float      # 0.0 to 1.0
    description: str
    location: Optional[int]
    code_snippet: Optional[str]
    root_cause: str
    suggestion: str
    fix_example: str

    def generate_report(self) -> str:
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append(f"BUG PATTERN DETECTED: {self.pattern_type.value.upper()}")
        lines.append("=" * 70)
        lines.append(f"\nSeverity: {self.severity.upper()}")
        lines.append(f"Confidence: {self.confidence * 100:.0f}%")
        if self.location:
            lines.append(f"\nLocation: Line {self.location}")
        lines.append(f"\nDescription:\n  {self.description}")
        lines.append(f"\nRoot Cause:")
        for ln in self.root_cause.split("\n"):
            if ln:
                lines.append(f"  {ln}")
        lines.append(f"\nHow to Fix:")
        for ln in self.suggestion.split("\n"):
            if ln:
                lines.append(f"  {ln}")
        lines.append(f"\nExample:")
        for ln in self.fix_example.split("\n"):
            if ln:
                lines.append(f"  {ln}")
        lines.append("\n" + "=" * 70)
        return "\n".join(lines)


class BugPatternDetector:
    """Detect bug patterns from a DebugReport."""

    def __init__(self, debug_report):
        self.report = debug_report
        self.patterns: List[DetectedPattern] = []

    def analyze(self) -> List[DetectedPattern]:
        self.patterns = []

        # Some patterns are always worth checking (resource leaks, mutating
        # iteration) regardless of whether code raised.
        self._detect_resource_leaks()
        self._detect_resource_leak_on_exception()
        self._detect_mutating_iterator()
        self._detect_aliasing()
        self._detect_silent_exception_swallow()

        # Exception-driven patterns
        if self.report.exception_info:
            exc_type = self.report.exception_info.get("exception_type")
            if exc_type is IndexError:
                self._detect_off_by_one()
            elif exc_type is KeyError:
                self._detect_missing_null_check()
            elif exc_type is TypeError:
                self._detect_type_confusion()
            elif exc_type is ZeroDivisionError:
                self._detect_division_by_zero()
            else:
                # Real gap found by direct testing: the four branches above
                # are a closed set. Any other unhandled exception (NameError,
                # AttributeError, ValueError, a custom exception, ...) fell
                # through with no pattern added at all, even though
                # exception_info demonstrably captured a real crash -- which
                # meant Phase1RuntimeDebug.run()'s `passed = len(patterns)==0`
                # reported `passed=True` for code that crashes on every call.
                # Confirmed directly: `undefined_variable_reference_xyz` in a
                # function body raised NameError, exception_info captured it
                # correctly, and patterns_found was still `[]`. This branch
                # is the fallback that closes that gap for every exception
                # type this class doesn't have a specialized detector for.
                self._detect_unhandled_exception()

        return self.patterns

    def _detect_unhandled_exception(self):
        """Fallback for any exception type without a specialized detector
        above. Deliberately generic (no root-cause guess beyond what the
        exception itself states) since, unlike IndexError/KeyError/
        TypeError/ZeroDivisionError, there's no single common cause to
        name for an arbitrary exception class -- but "the traced execution
        crashed" is itself always worth surfacing as a finding, not silence.
        """
        exc_type = self.report.exception_info.get("exception_type")
        exc_value = self.report.exception_info.get("exception_value")
        message = self.report.exception_info.get("message") or str(exc_value or "")
        type_name = getattr(exc_type, "__name__", str(exc_type))

        self.patterns.append(DetectedPattern(
            pattern_type=BugPatternType.UNHANDLED_EXCEPTION,
            severity="high",
            confidence=1.0,  # the exception is a directly observed fact, not an inference
            description=f"Execution raised an unhandled {type_name}: {message}",
            location=None,
            code_snippet=None,
            root_cause=(
                f"The traced code raised {type_name} and nothing in the call "
                f"path caught it, so execution terminated abnormally."
            ),
            suggestion=(
                "Determine whether this exception is expected for the given "
                "input (in which case it should be caught and handled "
                "explicitly, or the input should be rejected earlier with a "
                "clearer error) or whether it indicates a genuine defect in "
                "the traced code path."
            ),
            fix_example=(
                f"try:\n    ...\nexcept {type_name} as e:\n"
                f"    # handle or re-raise with more context\n    raise"
            ),
        ))

    # ------------------------------------------------------------------
    # Individual detectors
    # ------------------------------------------------------------------

    def _detect_off_by_one(self):
        code = self.report.code or ""
        snippet = self.report.exception_line or ""

        # Pattern 1: range(...len(...)+1...)
        if re.search(r"range\([^)]*len\([^)]*\)\s*\+\s*1[^)]*\)", code):
            self.patterns.append(DetectedPattern(
                pattern_type=BugPatternType.OFF_BY_ONE,
                severity="high",
                confidence=0.90,
                description="Loop index exceeds array bounds (off-by-one error)",
                location=None,
                code_snippet=snippet,
                root_cause=(
                    "range(..., len(arr)+1) includes index == len(arr),\n"
                    "but valid indices are 0 to len(arr)-1."
                ),
                suggestion=(
                    "Fix the range bounds:\n"
                    "  - for i in range(len(arr)): indices 0 to len-1\n"
                    "  - for i in range(1, len(arr)): indices 1 to len-1\n"
                    "  - Better: for item in arr (no indices needed)"
                ),
                fix_example=(
                    "# Wrong:\n"
                    "for i in range(1, len(arr)+1):\n"
                    "    arr[i]  # IndexError when i == len(arr)\n\n"
                    "# Right:\n"
                    "for i in range(1, len(arr)):\n"
                    "    arr[i]"
                ),
            ))

        # Pattern 2: while i <= len(...)
        if re.search(r"while\s+\w+\s*<=\s*len\(", code):
            self.patterns.append(DetectedPattern(
                pattern_type=BugPatternType.OFF_BY_ONE,
                severity="high",
                confidence=0.85,
                description="While loop uses <= len(...) instead of < len(...) (off-by-one)",
                location=None,
                code_snippet=snippet,
                root_cause=(
                    "while i <= len(arr) iterates one extra time;\n"
                    "valid indices stop at len(arr) - 1."
                ),
                suggestion="Use < instead of <= when comparing index to len(arr).",
                fix_example=(
                    "# Wrong:\n"
                    "while i <= len(arr):\n"
                    "    arr[i]\n\n"
                    "# Right:\n"
                    "while i < len(arr):\n"
                    "    arr[i]"
                ),
            ))

    def _detect_missing_null_check(self):
        if not self.report.exception_info:
            return
        exc_type = self.report.exception_info.get("exception_type")
        exc_value = self.report.exception_info.get("exception_value")
        if exc_type is not KeyError:
            return
        snippet = self.report.exception_line or ""
        key_str = str(exc_value).strip("'\"")

        self.patterns.append(DetectedPattern(
            pattern_type=BugPatternType.NULL_CHECK,
            severity="high",
            confidence=0.95,
            description=f"Accessing missing dictionary key '{key_str}' without checking",
            location=None,
            code_snippet=snippet,
            root_cause=(
                f"Code reads dict['{key_str}'] but the key isn't present.\n"
                "No existence check before access."
            ),
            suggestion=(
                "Check existence or provide a default:\n"
                "  - if key in d: value = d[key]\n"
                "  - value = d.get(key, default)\n"
                "  - from collections import defaultdict"
            ),
            fix_example=(
                "# Wrong:\n"
                f"value = data['{key_str}']  # KeyError if missing\n\n"
                "# Right:\n"
                f"value = data.get('{key_str}', default_value)"
            ),
        ))

    def _detect_type_confusion(self):
        if not self.report.exception_info:
            return
        exc_type = self.report.exception_info.get("exception_type")
        exc_value = self.report.exception_info.get("exception_value")
        if exc_type is not TypeError:
            return
        snippet = self.report.exception_line or ""
        msg = str(exc_value)

        self.patterns.append(DetectedPattern(
            pattern_type=BugPatternType.TYPE_CONFUSION,
            severity="high",
            confidence=0.80,
            description=f"Type mismatch: {msg}",
            location=None,
            code_snippet=snippet,
            root_cause=(
                "Operation between incompatible types.\n"
                f"Example: {msg}"
            ),
            suggestion=(
                "Convert or guard types:\n"
                "  - int(string), str(number), float(value)\n"
                "  - isinstance(x, expected_type) before use"
            ),
            fix_example=(
                "# Wrong:\n"
                "result = '5' + 5  # str + int\n\n"
                "# Right:\n"
                "result = int('5') + 5      # 10\n"
                "result = '5' + str(5)      # '55'"
            ),
        ))

    def _detect_division_by_zero(self):
        snippet = self.report.exception_line or ""
        self.patterns.append(DetectedPattern(
            pattern_type=BugPatternType.DIVISION_BY_ZERO,
            severity="critical",
            confidence=0.99,
            description="Division by zero",
            location=None,
            code_snippet=snippet,
            root_cause="Division requires a non-zero divisor; the divisor was zero.",
            suggestion=(
                "Guard the division:\n"
                "  - if divisor != 0: result = num / divisor\n"
                "  - try: result = n / d\n    except ZeroDivisionError: result = 0\n"
                "  - result = num / max(divisor, 1)  # only if zero floor is OK"
            ),
            fix_example=(
                "# Wrong:\n"
                "result = numerator / divisor\n\n"
                "# Right:\n"
                "if divisor != 0:\n"
                "    result = numerator / divisor\n"
                "else:\n"
                "    result = 0  # or raise"
            ),
        ))

    def _detect_aliasing(self):
        """Flag variables sharing a mutable object id when at least one was mutated."""
        if not self.report.timeline:
            return

        # Find the index where an alias was first observed and remember
        # the values at that point.
        alias_first_idx = None
        for i, e in enumerate(self.report.timeline):
            if e.aliases:
                alias_first_idx = i
                break
        if alias_first_idx is None:
            return

        first_event = self.report.timeline[alias_first_idx]
        alias_names = set()
        for group in (first_event.aliases or []):
            alias_names.update(group["variables"])
        if not alias_names:
            return

        baseline_repr = {
            n: repr(first_event.variables_after.get(n))
            for n in alias_names
            if first_event.variables_after and n in first_event.variables_after
        }

        # Compare baseline against later "line" events and the final state.
        # If any aliased var's repr changed, we treat that as mutation.
        mutated = False
        for e in self.report.timeline[alias_first_idx + 1 :]:
            if e.event_type != "line" or not e.variables_after:
                continue
            for n in alias_names:
                if n in e.variables_after and n in baseline_repr:
                    if repr(e.variables_after[n]) != baseline_repr[n]:
                        mutated = True
                        break
            if mutated:
                break

        if not mutated:
            # Final state is the post-last-line snapshot; check there too.
            final = getattr(self.report, "final_state", {}) or {}
            for n in alias_names:
                if n in final and n in baseline_repr:
                    if repr(final[n]) != baseline_repr[n]:
                        mutated = True
                        break

        if not mutated:
            return

        var_str = ", ".join(sorted(alias_names))
        self.patterns.append(DetectedPattern(
            pattern_type=BugPatternType.ALIASING,
            severity="high",
            confidence=0.95,
            description=f"Aliasing mutation: {var_str} reference the same object",
            location=None,
            code_snippet=None,
            root_cause=(
                f"Variables {var_str} share one object.\n"
                "Mutating one mutates all (e.g., y = x then y.append(...))."
            ),
            suggestion=(
                "Make a copy before mutating:\n"
                "  - y = x.copy()\n"
                "  - y = list(x)  /  y = dict(x)\n"
                "  - import copy; y = copy.deepcopy(x)  # nested structures"
            ),
            fix_example=(
                "# Wrong (aliasing):\n"
                "x = [1, 2, 3]\n"
                "y = x\n"
                "y.append(4)  # x ALSO becomes [1,2,3,4]\n\n"
                "# Right (copy):\n"
                "y = x.copy()\n"
                "y.append(4)  # x stays [1,2,3]"
            ),
        ))

    def _detect_resource_leaks(self):
        code = self.report.code or ""
        if "open(" not in code:
            return
        with_open_count = len(re.findall(r"\bwith\s+open\s*\(", code))
        open_count = len(re.findall(r"\bopen\s*\(", code))
        if open_count > with_open_count:
            self.patterns.append(DetectedPattern(
                pattern_type=BugPatternType.RESOURCE_LEAK,
                severity="medium",
                confidence=0.85,
                description="File opened without `with` (not guaranteed to close)",
                location=None,
                code_snippet=None,
                root_cause=(
                    "Bare open() leaks the file handle if an exception fires before close()."
                ),
                suggestion=(
                    "Use a context manager:\n"
                    "  with open('file.txt') as f:\n"
                    "      data = f.read()"
                ),
                fix_example=(
                    "# Wrong:\n"
                    "f = open('file.txt')\n"
                    "data = f.read()\n"
                    "f.close()\n\n"
                    "# Right:\n"
                    "with open('file.txt') as f:\n"
                    "    data = f.read()"
                ),
            ))

    def _detect_mutating_iterator(self):
        code = self.report.code or ""
        if re.search(r"for\s+\w+\s+in\s+range\(\s*len\(", code) and re.search(r"\.(pop|remove)\s*\(", code):
            self.patterns.append(DetectedPattern(
                pattern_type=BugPatternType.MUTATING_ITERATOR,
                severity="high",
                confidence=0.90,
                description="Modifying list while iterating (pop/remove during for loop)",
                location=None,
                code_snippet=None,
                root_cause=(
                    "Mutating a list while iterating skips elements and produces unpredictable behavior."
                ),
                suggestion=(
                    "Choose one:\n"
                    "  - Iterate backwards: for i in range(len(arr)-1, -1, -1)\n"
                    "  - Iterate over a copy: for item in arr[:]\n"
                    "  - Build a new list: arr = [x for x in arr if cond]"
                ),
                fix_example=(
                    "# Wrong:\n"
                    "for i in range(len(arr)):\n"
                    "    if arr[i] % 2 == 0:\n"
                    "        arr.pop(i)\n\n"
                    "# Right:\n"
                    "arr = [x for x in arr if x % 2 != 0]"
                ),
            ))

    def _detect_resource_leak_on_exception(self):
        """Detect when .close() is in try body instead of finally (exception leak)."""
        code = self.report.code or ""
        
        # Pattern: .close() inside try block but not in finally
        # This is a distinct pattern from "no with statement" because the code DOES
        # call close(), but at the wrong scope.
        try_blocks = re.findall(r"try\s*:(.+?)(?=except|finally|$)", code, re.DOTALL)
        has_finally = "finally:" in code
        
        for block in try_blocks:
            if re.search(r"\.close\s*\(", block):
                # Found .close() in try body
                if not has_finally:
                    self.patterns.append(DetectedPattern(
                        pattern_type=BugPatternType.RESOURCE_LEAK_ON_EXCEPTION,
                        severity="high",
                        confidence=0.85,
                        description="Resource .close() in try body, not in finally (leaks on exception)",
                        location=None,
                        code_snippet=None,
                        root_cause=(
                            "If an exception occurs before .close() is reached,\n"
                            "the resource is never cleaned up. Only finally blocks\n"
                            "execute unconditionally."
                        ),
                        suggestion=(
                            "Move .close() to finally block:\n"
                            "  try:\n"
                            "      resource = open(...)\n"
                            "      do_work(resource)\n"
                            "  finally:\n"
                            "      resource.close()\n\n"
                            "Or better: use a context manager (with statement)"
                        ),
                        fix_example=(
                            "# Wrong:\n"
                            "doc = fitz.open('file.pdf')\n"
                            "try:\n"
                            "    text = doc[0].get_text()\n"
                            "    doc.close()  # Never runs if exception above\n"
                            "except Exception:\n"
                            "    pass\n\n"
                            "# Right:\n"
                            "doc = fitz.open('file.pdf')\n"
                            "try:\n"
                            "    text = doc[0].get_text()\n"
                            "finally:\n"
                            "    doc.close()  # Always runs"
                        ),
                    ))
                    break

    def _detect_silent_exception_swallow(self):
        """Detect bare except: or except Exception: with no logging."""
        code = self.report.code or ""
        
        # Pattern 1: bare except:
        if re.search(r"except\s*:\s*(?:pass|return|$)", code):
            self.patterns.append(DetectedPattern(
                pattern_type=BugPatternType.SILENT_EXCEPTION,
                severity="medium",
                confidence=0.75,
                description="Bare except: clause silences all exceptions (could hide real bugs)",
                location=None,
                code_snippet=None,
                root_cause=(
                    "Bare except: catches everything including KeyboardInterrupt and SystemExit,\n"
                    "and provides no visibility into what went wrong."
                ),
                suggestion=(
                    "Catch specific exceptions and log them:\n"
                    "  try: code()\n"
                    "  except ValueError as e:\n"
                    "      logger.error(f'Invalid input: {e}')"
                ),
                fix_example=(
                    "# Wrong:\n"
                    "try:\n"
                    "    value = dangerous_op()\n"
                    "except:\n"
                    "    pass  # What went wrong? No one knows.\n\n"
                    "# Right:\n"
                    "try:\n"
                    "    value = dangerous_op()\n"
                    "except ValueError as e:\n"
                    "    logger.warning(f'Invalid input: {e}')\n"
                    "    value = default_value"
                ),
            ))
        
        # Pattern 2: except Exception: with only return/pass
        if re.search(r"except\s+Exception\s*:\s*(?:pass|return\s+None)", code):
            self.patterns.append(DetectedPattern(
                pattern_type=BugPatternType.SILENT_EXCEPTION,
                severity="medium",
                confidence=0.70,
                description="except Exception: with no logging hides errors",
                location=None,
                code_snippet=None,
                root_cause=(
                    "Code catches and silently ignores broad exceptions.\n"
                    "Good for intentional suppression, but risky without logging."
                ),
                suggestion=(
                    "At minimum, log the exception:\n"
                    "  except Exception as e:\n"
                    "      import logging\n"
                    "      logging.debug(f'Suppressed: {e}')\n"
                    "      return None"
                ),
                fix_example=(
                    "# Questionable:\n"
                    "try:\n"
                    "    return extract_image()\n"
                    "except Exception:\n"
                    "    return None  # Silent failure\n\n"
                    "# Better:\n"
                    "try:\n"
                    "    return extract_image()\n"
                    "except Exception as e:\n"
                    "    import logging\n"
                    "    logging.debug(f'Image extraction failed: {e}')\n"
                    "    return None"
                ),
            ))

    # ------------------------------------------------------------------
    # Combined report
    # ------------------------------------------------------------------

    def generate_combined_report(self) -> str:
        if not self.patterns:
            return "No bug patterns detected."

        lines = []
        lines.append("\n" + "=" * 70)
        lines.append(f"BUG PATTERN ANALYSIS - {len(self.patterns)} PATTERN(S) FOUND")
        lines.append("=" * 70)

        by_severity = {"critical": [], "high": [], "medium": [], "low": []}
        for p in self.patterns:
            by_severity.setdefault(p.severity, []).append(p)

        markers = {"critical": "[CRITICAL]", "high": "[HIGH]", "medium": "[MEDIUM]", "low": "[LOW]"}
        for sev in ("critical", "high", "medium", "low"):
            group = by_severity.get(sev, [])
            if group:
                lines.append(f"\n{markers[sev]} ({len(group)}):")
                for p in group:
                    lines.append(f"  - {p.pattern_type.value}")

        lines.append("\n" + "=" * 70)
        lines.append("Detailed Analysis:")
        lines.append("=" * 70)
        for i, p in enumerate(self.patterns, 1):
            lines.append(f"\n[{i}] {p.pattern_type.value.upper()}")
            lines.append(f"    Confidence: {p.confidence * 100:.0f}%")
            lines.append(f"    {p.description}")
            first_fix_line = p.suggestion.split("\n")[0]
            lines.append(f"\n    Fix: {first_fix_line}")

        lines.append("\n" + "=" * 70)
        return "\n".join(lines)


if __name__ == "__main__":
    from debug_report import execute_with_debug

    code = """
arr = [1, 2, 3]
for i in range(1, len(arr)+1):
    x = arr[i]
"""
    report = execute_with_debug(code)
    detector = BugPatternDetector(report)
    detector.analyze()
    print(detector.generate_combined_report())
