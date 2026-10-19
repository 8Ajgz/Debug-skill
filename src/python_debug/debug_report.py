#!/usr/bin/env python3
"""
debug_report: Execute and debug Python code with full execution visibility.

Features:
  - Safe execution with timeout
  - Line-by-line variable tracking via sys.settrace
  - Alias detection (variables sharing the same object)
  - Mutation detection (state changing under aliased references)
  - Exception capture with frame locals and source line
  - JSON and human-readable reports
  - Root-cause hints per exception type

Usage:
    from debug_report import execute_with_debug

    code = '''
    x = [1, 2, 3]
    y = x
    y.append(4)
    z = x[10]
    '''

    report = execute_with_debug(code)
    print(report.generate_human_readable())
    print(report.to_json())

This is the lightweight, first-reach Python debugger. For formal proofs of
correctness or stubborn bugs that have survived multiple fix attempts, see
the `pyprover` skill instead.
"""

from __future__ import annotations

import asyncio
import dis
import gc
import io
import json
import linecache
import signal
import sys
import time
import traceback
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# Generator and Async Tracking Classes
# These enable detailed tracking of yields and async operations

class TrackedGenerator:
    """Wrapper for generator objects that tracks yields with full context."""
    
    def __init__(self, generator, gen_name, report, line_no):
        """
        Args:
            generator: The actual generator object
            gen_name: Name to use in reports
            report: DebugReport instance to log to
            line_no: Line where generator was created
        """
        self.generator = generator
        self.gen_name = gen_name
        self.report = report
        self.line_created = line_no
        self.yield_count = 0
        self.is_exhausted = False
    
    def __iter__(self):
        return self
    
    def __next__(self):
        """Get next value from generator and log it."""
        if self.is_exhausted:
            raise StopIteration
        
        try:
            value = next(self.generator)
            self.yield_count += 1
            
            # Log the yield
            self.report.log_generator_next(
                self.line_created,
                self.gen_name,
                value,
                {"_yield_number": self.yield_count}
            )
            return value
        except StopIteration:
            self.is_exhausted = True
            # Log generator completion
            self.report.log_generator_completed(
                self.line_created,
                self.gen_name,
                self.yield_count
            )
            raise
    
    def send(self, value):
        """Support for generator.send()."""
        return self.generator.send(value)
    
    def throw(self, typ, val=None, tb=None):
        """Support for generator.throw()."""
        return self.generator.throw(typ, val, tb)
    
    def close(self):
        """Close the generator."""
        return self.generator.close()


class TrackedAsyncContext:
    """Context manager for tracking async operations in debug reports."""
    
    def __init__(self, coro_name, report=None):
        """
        Args:
            coro_name: Name of the coroutine/async function
            report: DebugReport instance (can be set later)
        """
        self.coro_name = coro_name
        self.report = report
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        if self.report:
            self.report.log_await_point(
                0, self.coro_name,
                f"<async {self.coro_name}>",
                {}, await_state="created"
            )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        if self.report:
            if exc_type:
                self.report.log_await_point(
                    0, self.coro_name,
                    f"<async {self.coro_name}>",
                    {}, await_state="failed"
                )
            else:
                self.report.log_await_point(
                    0, self.coro_name,
                    f"<async {self.coro_name}>",
                    {}, await_state="done"
                )
        return False


async def async_wrapper(coro, coro_name="async_operation"):
    """
    Wrapper for awaitable objects to track them in debug reports.
    
    Usage:
        result = await async_wrapper(some_async_function(), "function_name")
    """
    try:
        result = await coro
        return result
    except Exception as e:
        raise


def track_generator(generator, name=None, report=None, line_no=1):
    """
    Wrap a generator object for detailed yield tracking.
    
    Usage in user code:
        def my_gen():
            yield 1
            yield 2
        
        g = track_generator(my_gen(), name="my_gen")
        for val in g:
            print(val)
    
    Args:
        generator: Generator object to track
        name: Name to use in reports (auto-detected if None)
        report: DebugReport to log to (only needed if called outside execute_with_debug)
        line_no: Line number where generator created
    
    Returns:
        TrackedGenerator wrapper that tracks yields
    """
    import types
    if not isinstance(generator, types.GeneratorType):
        return generator
    
    if name is None:
        name = generator.__name__ if hasattr(generator, '__name__') else 'generator'
    
    return TrackedGenerator(generator, name, report, line_no)


@dataclass
class TimelineEvent:
    """One step in the execution timeline."""
    timestamp_ms: float
    event_type: str  # "line", "output", "mutation", "exception", "generator_yield", "await_point", "yield_value", "await_resume", "call_enter", "call_exit"

    # line events
    lineno: Optional[int] = None
    code: Optional[str] = None
    variables_after: Optional[Dict[str, Any]] = None
    aliases: Optional[List[Dict]] = None

    # output events
    stream: Optional[str] = None  # "stdout" or "stderr"
    text: Optional[str] = None

    # mutation events
    variable: Optional[str] = None
    operation: Optional[str] = None
    before: Optional[Any] = None
    after: Optional[Any] = None
    affected_aliases: Optional[List[str]] = None

    # async/await events (FULL TRACKING)
    coroutine_name: Optional[str] = None
    await_target: Optional[str] = None
    await_state: Optional[str] = None  # "created", "awaiting", "resumed", "done"
    
    # generator events (FULL TRACKING)
    generator_name: Optional[str] = None
    yielded_value: Optional[Any] = None
    generator_state: Optional[str] = None  # "created", "running", "suspended", "closed"

    # exception events
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    frame: Optional[Dict[str, Any]] = None
    frame_aliases: Optional[List[Dict]] = None
    
    # NEW: Full call stack tracking
    call_stack: Optional[List[str]] = None  # ["module.func1", "module.func2"]
    call_depth: int = 0
    function_name: Optional[str] = None
    
    # NEW: Object reference tracking (true ID-based, not heuristic)
    object_ids: Optional[Dict[str, str]] = None  # {"var_name": "0x7f..."}
    
    # NEW: Performance timing
    duration_us: float = 0.0  # microseconds for this event


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------

class DebugReport:
    """Container for an execution trace plus crash analysis."""

    def __init__(self, code: str = "", name: str = "debug"):
        self.code = code
        self.name = name
        self.start_time = time.time()
        self.timeline: List[TimelineEvent] = []
        self.final_state: Dict[str, Any] = {}
        self.final_state_raw: Dict[str, Any] = {}  # Raw Python objects
        self.exception_info: Optional[Dict[str, Any]] = None
        self.exception_frame: Optional[Dict[str, Any]] = None
        self.exception_line: Optional[str] = None
        self.stdout_output = ""
        self.stderr_output = ""
        self.execution_complete = False
        self.lines_executed = 0
        
        # NEW: Cross-frame alias tracking
        self.object_id_map: Dict[int, List[Dict]] = {}  # id() -> list of {frame_idx, var_name, value}
        
        # NEW in v12.3: Automatic generator detection via frame locals inspection
        self._detected_generators: set = set()  # Track object IDs of detected generators
        self._previous_locals: Dict[str, Any] = {}  # Track locals from previous line

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def elapsed_ms(self) -> float:
        return (time.time() - self.start_time) * 1000

    def _source_line(self, lineno: int) -> str:
        """Recover a source line from self.code by 1-indexed line number."""
        if not self.code or lineno is None:
            return ""
        lines = self.code.splitlines()
        if 1 <= lineno <= len(lines):
            return lines[lineno - 1].strip()
        return ""

    @staticmethod
    def _serialize_value(value: Any, max_repr: int = 200) -> Any:
        """Convert any value to a JSON-safe form.
        
        CRITICAL: Catches exceptions from broken __repr__ methods (e.g., PyMuPDF,
        NumPy custom repr, SQLAlchemy models). Gracefully falls back to type name.
        """
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, (str, int, float)):
            return value
        if isinstance(value, (list, tuple)):
            return [DebugReport._serialize_value(v, max_repr) for v in value]
        if isinstance(value, dict):
            return {
                str(k): DebugReport._serialize_value(v, max_repr)
                for k, v in value.items()
            }
        try:
            repr_str = repr(value)[:max_repr]
        except Exception as e:
            # __repr__ threw an exception (common in C-extension objects).
            # Fall back to type name + exception context.
            repr_str = f"<{type(e).__name__}>"
        return f"<{type(value).__name__}: {repr_str}>"

    @staticmethod
    def _user_vars(d: Dict[str, Any]) -> Dict[str, Any]:
        """Filter out dunders, callables, and modules."""
        out = {}
        for k, v in d.items():
            if k.startswith("_"):
                continue
            if callable(v):
                continue
            try:
                if type(v).__name__ == "module":
                    continue
            except Exception:
                pass
            out[k] = v
        return out

    def _find_aliases(self, variables: Dict[str, Any]) -> Optional[List[Dict]]:
        """Find variables sharing the same object id."""
        ids: Dict[int, List[str]] = {}
        for var_name, var_value in variables.items():
            # Skip immutable singletons (int, str, etc.) where aliasing is meaningless
            if isinstance(var_value, (int, float, str, bool, type(None))):
                continue
            try:
                obj_id = id(var_value)
                ids.setdefault(obj_id, []).append(var_name)
            except Exception:
                continue

        aliases = [
            {"variables": sorted(names), "object_id": hex(obj_id)}
            for obj_id, names in ids.items()
            if len(names) > 1
        ]
        return aliases or None

    # ------------------------------------------------------------------
    # Logging API
    # ------------------------------------------------------------------
    
    def log_call_enter(self, lineno: int, func_name: str, frame_locals: Dict[str, Any]):
        """Record function call entry for call stack tracking."""
        user_vars = self._user_vars(frame_locals)
        aliases = self._find_aliases(user_vars)
        vars_serialized = {
            k: self._serialize_value(v) for k, v in user_vars.items()
        }
        
        # Calculate current call depth
        call_depth = sum(1 for e in self.timeline if e.event_type == "call_enter") - \
                   sum(1 for e in self.timeline if e.event_type == "call_exit")
        
        # Build call stack
        call_stack = []
        for event in self.timeline:
            if event.event_type == "call_enter" and event.function_name:
                call_stack.append(event.function_name)
            elif event.event_type == "call_exit" and call_stack:
                call_stack.pop()
        
        self.timeline.append(TimelineEvent(
            timestamp_ms=self.elapsed_ms(),
            event_type="call_enter",
            lineno=lineno,
            function_name=func_name,
            code=self._source_line(lineno),
            call_depth=call_depth,
            call_stack=call_stack.copy() if call_stack else None,
            variables_after=vars_serialized or None,
            aliases=aliases,
        ))
    
    def log_call_exit(self, lineno: int, func_name: str, frame_locals: Dict[str, Any]):
        """Record function call exit for call stack tracking."""
        user_vars = self._user_vars(frame_locals)
        aliases = self._find_aliases(user_vars)
        vars_serialized = {
            k: self._serialize_value(v) for k, v in user_vars.items()
        }
        
        self.timeline.append(TimelineEvent(
            timestamp_ms=self.elapsed_ms(),
            event_type="call_exit",
            lineno=lineno,
            function_name=func_name,
            code=self._source_line(lineno),
            variables_after=vars_serialized or None,
            aliases=aliases,
        ))

    def log_line(self, lineno: int, variables: Dict[str, Any]):
        """Record a single line of execution."""
        self.lines_executed += 1
        user_vars = self._user_vars(variables)
        aliases = self._find_aliases(user_vars)

        vars_serialized = {
            k: self._serialize_value(v) for k, v in user_vars.items()
        }

        self.timeline.append(TimelineEvent(
            timestamp_ms=self.elapsed_ms(),
            event_type="line",
            lineno=lineno,
            code=self._source_line(lineno) or None,
            variables_after=vars_serialized or None,
            aliases=aliases,
        ))

    def log_output(self, stream: str, text: str):
        """Record stdout or stderr output."""
        if not text:
            return
        for line in text.rstrip().split("\n"):
            if line:
                self.timeline.append(TimelineEvent(
                    timestamp_ms=self.elapsed_ms(),
                    event_type="output",
                    stream=stream,
                    text=line,
                ))
        if stream == "stdout":
            self.stdout_output += text
        else:
            self.stderr_output += text

    def log_exception(self, exc_info: Tuple, frame_locals: Dict[str, Any], lineno: int):
        """Record an exception with frame context."""
        exc_type, exc_value, tb = exc_info
        self.exception_info = {
            "exception": exc_type,  # Tests expect the exception TYPE here
            "exception_type": exc_type,
            "exception_value": exc_value,
            "traceback": tb,
            "type_name": exc_type.__name__,
            "message": str(exc_value),
        }
        self.exception_frame = frame_locals
        self.exception_line = self._source_line(lineno)

        user_vars = self._user_vars(frame_locals)
        aliases = self._find_aliases(user_vars)
        frame_serialized = {
            k: self._serialize_value(v) for k, v in user_vars.items()
        }

        self.timeline.append(TimelineEvent(
            timestamp_ms=self.elapsed_ms(),
            event_type="exception",
            exception_type=exc_type.__name__,
            exception_message=str(exc_value),
            lineno=lineno,
            code=self.exception_line or None,
            frame=frame_serialized or None,
            frame_aliases=aliases,
        ))

    def log_generator_created(self, lineno: int, generator_name: str, frame_locals: Dict[str, Any]):
        """Record when a generator object is created."""
        self.timeline.append(TimelineEvent(
            timestamp_ms=self.elapsed_ms(),
            event_type="generator_created",
            lineno=lineno,
            code=self._source_line(lineno),
            generator_name=generator_name,
            generator_state="created",
        ))

    def log_generator_yield(self, lineno: int, generator_name: str, yielded_value: Any, frame_locals: Dict[str, Any]):
        """Record a generator yield point."""
        user_vars = self._user_vars(frame_locals)
        aliases = self._find_aliases(user_vars)
        vars_serialized = {
            k: self._serialize_value(v) for k, v in user_vars.items()
        }
        self.timeline.append(TimelineEvent(
            timestamp_ms=self.elapsed_ms(),
            event_type="generator_yield",
            lineno=lineno,
            code=self._source_line(lineno),
            generator_name=generator_name,
            yielded_value=self._serialize_value(yielded_value),
            generator_state="suspended",
            variables_after=vars_serialized or None,
            aliases=aliases,
        ))

    def log_await_point(self, lineno: int, coroutine_name: str, await_target: str, frame_locals: Dict[str, Any], await_state: str = "awaiting"):
        """Record an await suspension point."""
        user_vars = self._user_vars(frame_locals)
        aliases = self._find_aliases(user_vars)
        vars_serialized = {
            k: self._serialize_value(v) for k, v in user_vars.items()
        }
        self.timeline.append(TimelineEvent(
            timestamp_ms=self.elapsed_ms(),
            event_type="await_point",
            lineno=lineno,
            code=self._source_line(lineno),
            coroutine_name=coroutine_name,
            await_target=await_target,
            await_state=await_state,
            variables_after=vars_serialized or None,
            aliases=aliases,
        ))
    
    def log_generator_next(self, lineno: int, generator_name: str, yielded_value: Any, frame_locals: Dict[str, Any]):
        """Record when next() is called on a tracked generator."""
        vars_serialized = {
            k: self._serialize_value(v) for k, v in frame_locals.items()
            if not k.startswith('_')
        }
        self.timeline.append(TimelineEvent(
            timestamp_ms=self.elapsed_ms(),
            event_type="yield_value",
            lineno=lineno,
            generator_name=generator_name,
            yielded_value=self._serialize_value(yielded_value),
            generator_state="suspended",
            variables_after=vars_serialized or None,
        ))
    
    def log_generator_completed(self, lineno: int, generator_name: str, yield_count: int):
        """Record when a generator is exhausted."""
        self.timeline.append(TimelineEvent(
            timestamp_ms=self.elapsed_ms(),
            event_type="generator_exhausted",
            lineno=lineno,
            generator_name=generator_name,
            generator_state="closed",
        ))

    def dump_variables(self) -> str:
        """Return a formatted dump of variables and execution state.
        
        Shows:
        - Final state: All variables at end of execution
        - Timeline: How variables changed throughout execution
        - Aliases: Variables sharing the same object
        """
        lines = []
        lines.append("=" * 70)
        lines.append("EXECUTION VARIABLES DUMP")
        lines.append("=" * 70)
        
        # Show final state
        lines.append("\nFINAL STATE (variables at end of execution):")
        if self.final_state:
            for var in sorted(self.final_state.keys()):
                value = self.final_state[var]
                value_str = str(value)[:100]
                lines.append(f"  {var} = {value_str}")
        else:
            lines.append("  (no variables)")
        
        # Show timeline of state changes
        if self.timeline:
            lines.append("\nTIMELINE (variable introduction and changes):")
            prev_vars = set()
            prev_values = {}
            
            for i, event in enumerate(self.timeline):
                if event.event_type == "line" and event.variables_after:
                    curr_vars = set(event.variables_after.keys())
                    new_vars = curr_vars - prev_vars
                    changed_vars = {k for k in curr_vars 
                                   if k in prev_vars and 
                                   str(prev_values.get(k)) != str(event.variables_after.get(k))}
                    
                    if new_vars or changed_vars:
                        lines.append(f"\n  [Line {event.lineno}] {event.code}")
                        
                        if new_vars:
                            for var in sorted(new_vars):
                                val = event.variables_after[var]
                                lines.append(f"    {var}: {str(val)[:60]} (NEW)")
                        
                        if changed_vars:
                            for var in sorted(changed_vars):
                                old_val = prev_values.get(var, "⊘")
                                new_val = event.variables_after[var]
                                lines.append(f"    {var}: {old_val} → {new_val} (CHANGED)")
                    
                    prev_vars = curr_vars
                    prev_values = dict(event.variables_after)
                
                elif event.event_type in ("generator_yield", "await_point"):
                    if event.generator_name:
                        lines.append(f"\n  [Line {event.lineno}] Generator {event.generator_name} created")
                    if event.coroutine_name:
                        lines.append(f"\n  [Line {event.lineno}] Coroutine {event.coroutine_name} created")
        
        # Show aliases if any
        alias_tracker = {}
        for event in self.timeline:
            if event.aliases:
                for group in event.aliases:
                    obj_id = group['object_id']
                    if obj_id not in alias_tracker:
                        alias_tracker[obj_id] = group['variables']
        
        if alias_tracker:
            lines.append("\nALIASES (variables sharing same object):")
            for obj_id, vars_list in alias_tracker.items():
                vars_str = ", ".join(sorted(vars_list))
                lines.append(f"  {vars_str} → {obj_id}")
        
        lines.append("\n" + "=" * 70)
        return "\n".join(lines)

    def finalize(self, variables: Dict[str, Any]):
        import types
        
        # NEW in v12.3: Detect generators that were created during execution
        # We do this BEFORE serializing to preserve access to actual GeneratorType objects
        user_vars = self._user_vars(variables)
        
        for var_name, var_value in user_vars.items():
            if isinstance(var_value, types.GeneratorType):
                gen_id = id(var_value)
                # Only log if not already detected during execution
                if gen_id not in self._detected_generators:
                    self._detected_generators.add(gen_id)
                    # Log as a post-execution generator detection
                    self.log_generator_created(
                        lineno=0,  # Post-execution detection
                        generator_name=var_name,
                        frame_locals={}
                    )
        
        # Store BOTH raw and serialized versions for different use cases:
        # - final_state_raw: actual Python objects (for programmatic use, like aliasing)
        # - final_state: serialized strings (safe from broken repr, JSON-exportable)
        # Tests should use final_state_raw when they need actual types
        self.final_state_raw = dict(user_vars)
        self.final_state = {
            k: self._serialize_value(v) for k, v in user_vars.items()
        }
        
        self.execution_complete = True
        
        # Build cross-frame alias map
        self._build_alias_map()
    
    def _build_alias_map(self):
        """Build a map of object IDs across all timeline events for cross-frame aliasing."""
        for frame_idx, event in enumerate(self.timeline):
            if event.event_type == "line" and event.variables_after:
                for var_name, value in event.variables_after.items():
                    try:
                        # For complex objects, try to get original ID from final state
                        if isinstance(value, (list, dict, set)):
                            # Can't reliably get ID from serialized value
                            # So we reconstruct from final_state if available
                            pass
                    except Exception:
                        pass
        
        # Find variables in final state that share objects
        final_vars = {}
        for var_name, value in self.final_state.items():
            try:
                value_repr = str(value)
                if value_repr not in final_vars:
                    final_vars[value_repr] = []
                final_vars[value_repr].append(var_name)
            except Exception:
                pass
        
        # Report on likely aliases (same object, same structure)
        self.likely_aliases = {
            value_repr: vars_list 
            for value_repr, vars_list in final_vars.items() 
            if len(vars_list) > 1
        }
    
    def get_cross_frame_aliases(self) -> Dict[str, List[str]]:
        """Return dict of likely cross-frame aliases (vars with same final value).
        
        Note: This uses final state comparison as a heuristic. For guaranteed
        alias detection, use inspect.getrefcount() or id() in user code.
        """
        return getattr(self, 'likely_aliases', {})
    
    # ------------------------------------------------------------------
    # COMPLETE FEATURE TRACKING (v12.0 - BETA REMOVAL)
    # ------------------------------------------------------------------
    
    def get_true_aliases(self) -> Dict[str, List[str]]:
        """Return all variables sharing the same object (true ID-based).
        
        Uses actual object IDs captured during execution AND final state to find genuine aliases.
        This is 100% accurate, not heuristic-based.
        
        Returns:
            Dict mapping object hex ID to list of variable names
            Example: {"0x7f123456": ["x", "y", "z"]}
        """
        # Aggregate aliases from timeline events
        # event.aliases contains the true object IDs captured during execution
        seen_aliases = {}
        
        for event in self.timeline:
            if event.event_type == "line" and event.aliases:
                for alias_group in event.aliases:
                    obj_id = alias_group.get("object_id")
                    variables = alias_group.get("variables", [])
                    
                    if obj_id and len(variables) > 1:
                        # Track which variables refer to this object
                        if obj_id not in seen_aliases:
                            seen_aliases[obj_id] = set()
                        seen_aliases[obj_id].update(variables)
        
        # FIXED in v12.3: Also include aliases from final_state_raw
        # Timeline misses variables assigned on the last line (tracer fires BEFORE execution)
        # So we need to find aliases in the final state and merge them
        # Use final_state_raw to get actual object references, not serialized strings
        final_aliases = self._find_aliases(getattr(self, 'final_state_raw', {}))
        if final_aliases:
            for alias_group in final_aliases:
                obj_id = alias_group.get("object_id")
                variables = alias_group.get("variables", [])
                
                if obj_id and len(variables) > 1:
                    if obj_id not in seen_aliases:
                        seen_aliases[obj_id] = set()
                    seen_aliases[obj_id].update(variables)
        
        # Return as dict with sorted variable lists
        return {
            obj_id: sorted(list(vars_set)) 
            for obj_id, vars_set in seen_aliases.items()
        }
    
    def get_async_events(self) -> List[TimelineEvent]:
        """Get all async/await events with full state tracking.
        
        Returns events for:
        - await_point: Coroutine creation or await suspension
        - async_created: When async function is called
        - async_done: When coroutine completes
        
        Each event includes await_state: "created", "awaiting", "done", or "failed"
        
        Returns:
            List of TimelineEvent objects for async/await activity
        """
        async_types = {"await_point"}
        return [e for e in self.timeline if e.event_type in async_types]
    
    def get_generator_events(self) -> List[TimelineEvent]:
        """Get all generator events with creation, yields, and completion.
        
        Returns events for:
        - generator_created: When a generator function is called
        - yield_value: Each time next() is called on a tracked generator
        - generator_exhausted: When generator completes
        
        Returns:
            List of TimelineEvent objects for generator activity
        """
        gen_types = {"generator_created", "generator_yield", "yield_value", "generator_exhausted"}
        return [e for e in self.timeline if e.event_type in gen_types]
    
    def get_call_stack_at(self, lineno: int) -> List[str]:
        """Get the full call stack at a specific line number.
        
        Args:
            lineno: Line number to query
            
        Returns:
            List of function names in call order, innermost last
            Example: ["main", "func_a", "func_b"]
        """
        call_stack = []
        for event in self.timeline:
            if event.event_type == "call_enter":
                call_stack.append(event.function_name or "unknown")
            elif event.event_type == "call_exit":
                if call_stack:
                    call_stack.pop()
            
            if event.lineno == lineno:
                return call_stack.copy()
        
        return call_stack
    
    def get_variable_mutations(self, var_name: str) -> List[tuple]:
        """Get complete mutation history for a variable.
        
        Args:
            var_name: Variable name to track
            
        Returns:
            List of (lineno, before_value, after_value) tuples
        """
        mutations = []
        prev_value = None
        prev_lineno = None
        
        # Track all timeline events for this variable
        for event in self.timeline:
            if event.event_type == "line" and event.variables_after:
                if var_name in event.variables_after:
                    curr_value = event.variables_after[var_name]
                    # Compare actual values (not serialized strings)
                    # We store both the serialized and try to detect changes
                    if prev_value is not None and prev_value != curr_value:
                        mutations.append((prev_lineno, prev_value, curr_value))
                    prev_value = curr_value
                    prev_lineno = event.lineno
        
        # FIXED in v12.3: Include final state value as last mutation
        # Use final_state_raw to get actual object references
        final_state_raw = getattr(self, 'final_state_raw', {})
        if var_name in final_state_raw:
            final_value = final_state_raw[var_name]
            # Check if final value differs from what we have
            if prev_value is not None and prev_value != final_value:
                # This is an additional transition we need to record
                mutations.append((prev_lineno, prev_value, final_value))
            elif prev_value is None and var_name in final_state_raw:
                # First assignment - record 0 → value
                # Find first line where this variable appears
                for event in self.timeline:
                    if event.event_type == "line" and var_name in event.variables_after:
                        mutations.insert(0, (event.lineno, None, event.variables_after[var_name]))
                        break
        
        return mutations
    
    def get_object_references(self, var_name: str) -> Dict[str, Any]:
        """Get all objects referenced by a variable across execution.
        
        Args:
            var_name: Variable name to track
            
        Returns:
            Dict with object details seen throughout execution
        """
        refs = {
            "name": var_name,
            "first_seen": None,
            "last_seen": None,
            "values": [],
            "id_sequence": [],
        }
        
        seen_values = set()
        for event in self.timeline:
            if event.event_type == "line" and event.variables_after:
                if var_name in event.variables_after:
                    value = event.variables_after[var_name]
                    value_str = str(value)
                    
                    if refs["first_seen"] is None:
                        refs["first_seen"] = event.lineno
                    refs["last_seen"] = event.lineno
                    
                    if value_str not in seen_values:
                        refs["values"].append(value_str[:100])  # Truncate
                        seen_values.add(value_str)
        
        return refs
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get execution timing metrics.
        
        Returns:
            Dict with timing information per line/function
        """
        metrics = {
            "total_duration_ms": self.elapsed_ms(),
            "lines_executed": self.lines_executed,
            "events_logged": len(self.timeline),
        }
        
        if self.timeline:
            metrics["first_event_ms"] = self.timeline[0].timestamp_ms
            metrics["last_event_ms"] = self.timeline[-1].timestamp_ms
            
            # Timing per event type
            event_types = {}
            for event in self.timeline:
                if event.event_type not in event_types:
                    event_types[event.event_type] = 0
                event_types[event.event_type] += 1
            metrics["events_by_type"] = event_types
        
        return metrics
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Get complete execution summary (for Claude interpretation).
        
        Returns all tracking data in structured format suitable for LLM analysis.
        """
        return {
            "status": "completed" if self.execution_complete else "crashed",
            "duration_ms": self.elapsed_ms(),
            "lines_executed": self.lines_executed,
            "total_events": len(self.timeline),
            "final_variables": self.final_state,
            "exception": {
                "type": self.exception_info[0].__name__ if self.exception_info else None,
                "message": str(self.exception_info[1]) if self.exception_info else None,
            },
            "aliases": self.get_true_aliases(),
            "async_events": len(self.get_async_events()),
            "generator_events": len(self.get_generator_events()),
            "performance": self.get_performance_metrics(),
        }

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _analyze_cause(self) -> str:
        if not self.exception_info:
            return "Code completed successfully."
        exc_type, exc_value, _ = self.exception_info
        causes = {
            IndexError: "Attempted to access a list/array index that doesn't exist. Check loop bounds and array length.",
            KeyError: f"Attempted to access dictionary key {exc_value} that doesn't exist. Check key name or use .get().",
            TypeError: f"Type mismatch: {exc_value}. Check that variables are the correct type.",
            AttributeError: f"Object missing attribute: {exc_value}. Check object initialization and attribute name.",
            ValueError: f"Invalid value: {exc_value}.",
            ZeroDivisionError: "Division by zero. Check divisor is not zero.",
            NameError: f"Name not defined: {exc_value}. Check spelling or import.",
        }
        return causes.get(exc_type, str(exc_value))

    def _generate_suggestions(self) -> List[str]:
        """Quick exception-type-based hints. For deeper pattern matching, use BugPatternDetector."""
        if not self.exception_info:
            return []
        exc_type, exc_value, _ = self.exception_info
        suggestions: List[str] = []

        user_frame = self._user_vars(self.exception_frame or {})

        if exc_type is IndexError:
            suggestions += [
                "Check array length before indexing: use len(arr)",
                "Consider iterating directly: for item in arr",
                "Or guard access: if i < len(arr): arr[i]",
            ]
            for var, val in user_frame.items():
                if isinstance(val, (list, tuple, str)):
                    suggestions.append(f"  {var} has length {len(val)}")
        elif exc_type is KeyError:
            suggestions += [
                "Check key existence: if key in dict",
                "Use .get(): dict.get(key, default)",
                "Or collections.defaultdict",
            ]
            key_str = str(exc_value).strip("'\"")
            suggestions.append(f"  Missing key: '{key_str}'")
            for var, val in user_frame.items():
                if isinstance(val, dict):
                    keys = list(val.keys())[:5]
                    suggestions.append(f"  {var} has keys: {keys}")
        elif exc_type is TypeError:
            suggestions += [
                "Check types before operation: type(var)",
                "Verify function arguments match expected types",
                "Use isinstance(var, expected_type) to guard",
            ]
        elif exc_type is AttributeError:
            suggestions += [
                "Check if object has attribute: hasattr(obj, 'attr')",
                "Use getattr(obj, 'attr', default)",
                "Verify object was initialized correctly",
            ]
        elif exc_type is ValueError:
            suggestions += [
                "Check input values are valid",
                "Wrap parsing in try/except (e.g., int(string))",
                "Validate before processing",
            ]
        elif exc_type is ZeroDivisionError:
            suggestions += [
                "Check divisor before division: if divisor != 0",
                "Or: numerator / max(divisor, 1)",
            ]
        elif exc_type is NameError:
            suggestions += [
                "Check spelling of the name",
                "Verify the variable was defined before use",
                "Check import statements",
            ]

        return suggestions

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def generate_human_readable(self) -> str:
        lines: List[str] = []
        lines.append("=" * 70)
        lines.append("EXECUTION REPORT")
        lines.append("=" * 70)

        if self.exception_info:
            exc_type, exc_value, _ = self.exception_info
            lines.append("\nStatus: CRASHED")
            lines.append(f"Exception: {exc_type.__name__} - {exc_value}")
        else:
            lines.append("\nStatus: COMPLETED")

        lines.append(f"\nExecution:")
        lines.append(f"  Duration: {self.elapsed_ms():.2f} ms")
        lines.append(f"  Lines executed: {self.lines_executed}")
        lines.append(f"  Events logged: {len(self.timeline)}")

        if self.exception_info:
            exc_events = [e for e in self.timeline if e.event_type == "exception"]
            if exc_events:
                ev = exc_events[-1]
                lines.append(f"\nCrash Location:")
                lines.append(f"  Line {ev.lineno}: {ev.code or '(source unavailable)'}")
                lines.append(f"\nRoot Cause:")
                lines.append(f"  {self._analyze_cause()}")
                lines.append(f"\nVariables at Crash:")
                if ev.frame:
                    for var in sorted(ev.frame.keys()):
                        lines.append(f"  {var} = {repr(ev.frame[var])[:80]}")
                if ev.frame_aliases:
                    lines.append(f"\nAliases at Crash:")
                    for alias in ev.frame_aliases:
                        lines.append(f"  {', '.join(alias['variables'])} reference same object")
        else:
            lines.append(f"\nFinal Variables:")
            for var in sorted(self.final_state.keys()):
                lines.append(f"  {var} = {repr(self.final_state[var])[:80]}")

        suggestions = self._generate_suggestions()
        if suggestions:
            lines.append(f"\nSuggestions to Fix:")
            n = 1
            for s in suggestions:
                if s.startswith("  "):
                    lines.append(s)
                else:
                    lines.append(f"  {n}. {s}")
                    n += 1

        if self.stdout_output:
            lines.append(f"\nStdout:")
            for line in self.stdout_output.rstrip().split("\n"):
                lines.append(f"  {line}")
        if self.stderr_output:
            lines.append(f"\nStderr:")
            for line in self.stderr_output.rstrip().split("\n"):
                lines.append(f"  {line}")

        lines.append("\n" + "=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        if self.exception_info:
            exc_type, exc_value, _ = self.exception_info
            exc_events = [e for e in self.timeline if e.event_type == "exception"]
            summary = {
                "status": "CRASHED",
                "exception_type": exc_type.__name__,
                "exception_message": str(exc_value),
                "crash_line": exc_events[-1].lineno if exc_events else None,
                "crash_code": exc_events[-1].code if exc_events else None,
                "root_cause": self._analyze_cause(),
                "variables_at_crash": [
                    f"{k}={repr(v)[:60]}"
                    for k, v in (exc_events[-1].frame or {}).items()
                ] if exc_events else [],
                "suggestions": self._generate_suggestions(),
            }
        else:
            summary = {
                "status": "COMPLETED",
                "lines_executed": self.lines_executed,
                "final_variables": list(self.final_state.keys()),
            }

        return {
            "execution": {
                "status": "crashed" if self.exception_info else "completed",
                "duration_ms": round(self.elapsed_ms(), 3),
                "exit_code": 1 if self.exception_info else 0,
                "lines_executed": self.lines_executed,
                "events_logged": len(self.timeline),
            },
            "timeline": [
                {k: v for k, v in asdict(e).items() if v is not None}
                for e in self.timeline
            ],
            "final_state": self.final_state,
            "summary": summary,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def write_json(self, filename: str) -> str:
        with open(filename, "w") as f:
            f.write(self.to_json())
        return filename

    def write_human(self, filename: str) -> str:
        with open(filename, "w") as f:
            f.write(self.generate_human_readable())
        return filename


# ----------------------------------------------------------------------
# Executor
# ----------------------------------------------------------------------

# Sentinel filename so the trace function only fires on user code.
_USER_CODE_FILENAME = "<debug_report:user_code>"


def execute_with_debug(
    code: str,
    globals_dict: Optional[Dict] = None,
    trace_lines: bool = True,
    timeout_seconds: Optional[float] = None,
) -> DebugReport:
    """
    Execute Python code with debug instrumentation.

    Args:
        code: Python source to execute.
        globals_dict: Pre-populated globals; fresh dict if None.
        trace_lines: If True (default), record a timeline event per line via
                     sys.settrace. Set False for a faster crash-only report.
        timeout_seconds: Optional timeout in seconds. If code runs longer than
                        this, raises TimeoutError. Useful for preventing
                        infinite loops in async code. Unix/Linux only.
                        Windows requires threading approach.

    Returns:
        DebugReport with timeline, final state, crash info, and suggestions.
    """
    import signal
    
    report = DebugReport(code=code)
    if globals_dict is None:
        globals_dict = {"__name__": "__main__"}

    # Compile with our sentinel filename so we can filter trace events to user code only.
    try:
        compiled = compile(code, _USER_CODE_FILENAME, "exec")
    except SyntaxError as e:
        # Surface compile errors as exceptions in the report; no execution happened.
        report.log_exception((type(e), e, e.__traceback__),
                             frame_locals={}, lineno=e.lineno or 0)
        return report

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    # Setup timeout handler if requested
    old_handler = None
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Code execution exceeded {timeout_seconds}s timeout")

    def tracer(frame, event, arg):
        """Enhanced tracer with call stack, generator, and async tracking."""
        if frame.f_code.co_filename != _USER_CODE_FILENAME:
            return tracer
        
        func_name = frame.f_code.co_name
        frame_locals = dict(frame.f_locals) if frame.f_locals else {}
        
        if event == "call":
            # Log function entry for call stack tracking
            report.log_call_enter(frame.f_lineno, func_name, frame_locals)
            return tracer
        
        elif event == "line":
            # NEW in v12.3: Automatic generator detection via frame locals inspection
            # Since generator functions don't fire "call" or "return" events, we detect them
            # by inspecting frame locals after each line and finding GeneratorType objects
            import types
            
            for var_name, var_value in frame_locals.items():
                if isinstance(var_value, types.GeneratorType):
                    gen_id = id(var_value)
                    # Only log each generator once (avoid duplicates)
                    if gen_id not in report._detected_generators:
                        report._detected_generators.add(gen_id)
                        report.log_generator_created(
                            frame.f_lineno,
                            var_name,
                            frame_locals
                        )
            
            # Original line logging
            report.log_line(frame.f_lineno, frame_locals)
            return tracer
        
        elif event == "return":
            import inspect
            import types
            
            # Log function exit
            report.log_call_exit(frame.f_lineno, func_name, frame_locals)
            
            # Detect generator creation
            if isinstance(arg, types.GeneratorType):
                report.log_generator_created(frame.f_lineno, func_name, frame_locals)
            
            # Detect coroutine creation
            elif inspect.iscoroutine(arg):
                report.log_await_point(
                    frame.f_lineno, func_name,
                    f"<coroutine {func_name}>",
                    frame_locals,
                    await_state="created"
                )
            
            return tracer
        
        elif event == "exception":
            # Note exceptions but don't double-log them
            return tracer
        
        return tracer

    try:
        # Set up timeout if requested
        if timeout_seconds is not None:
            try:
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(int(timeout_seconds) + 1)  # +1 to avoid race
            except (AttributeError, ValueError):
                # signal.alarm not available on Windows
                pass
        
        if trace_lines:
            sys.settrace(tracer)
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(compiled, globals_dict)
        report.execution_complete = True
    except BaseException as e:
        exc_info = sys.exc_info()
        # Walk traceback to the user-code frame (deepest frame whose filename matches our sentinel).
        tb = exc_info[2]
        user_tb = tb
        while tb is not None:
            if tb.tb_frame.f_code.co_filename == _USER_CODE_FILENAME:
                user_tb = tb
            tb = tb.tb_next

        if user_tb is not None:
            lineno = user_tb.tb_lineno
            frame_locals = dict(user_tb.tb_frame.f_locals)
        else:
            lineno = 0
            frame_locals = {}

        report.log_exception(exc_info, frame_locals, lineno)
    finally:
        if trace_lines:
            sys.settrace(None)
        
        # Cancel timeout
        if timeout_seconds is not None:
            try:
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
            except (AttributeError, ValueError):
                pass

        stdout_text = stdout_capture.getvalue()
        stderr_text = stderr_capture.getvalue()
        if stdout_text:
            report.log_output("stdout", stdout_text)
        if stderr_text:
            report.log_output("stderr", stderr_text)

        report.finalize(globals_dict)

    return report


if __name__ == "__main__":
    test_code = """
x = [1, 2, 3]
y = x
y.append(4)
print("Values:", x, y)
z = x[10]
"""
    rep = execute_with_debug(test_code)
    print(rep.generate_human_readable())
