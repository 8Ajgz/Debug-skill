#!/usr/bin/env python3
"""
Comprehensive Examples for python-debug v12.2

Demonstrates:
1. Generator tracking with track_generator()
2. Async context monitoring
3. Call stack analysis
4. Integration with pattern detection
5. Complete workflows
"""

from debug_report import (
    execute_with_debug, DebugReport, track_generator, 
    TrackedAsyncContext, TimelineEvent
)
from bug_patterns import BugPatternDetector


# =============================================================================
# EXAMPLE 1: Generator Tracking
# =============================================================================

def example_1_generator_tracking():
    """Track generator yields with full context."""
    print("\n" + "="*70)
    print("EXAMPLE 1: GENERATOR TRACKING")
    print("="*70)
    
    # Define a generator function
    def fibonacci(n):
        """Generate fibonacci sequence."""
        a, b = 0, 1
        for _ in range(n):
            yield a
            a, b = b, a + b
    
    # Create report
    report = DebugReport("fibonacci generator")
    
    # Wrap the generator for detailed tracking
    fib_tracked = track_generator(
        fibonacci(5),
        name="fibonacci_gen",
        report=report,
        line_no=1
    )
    
    # Consume the generator
    print("\nFibonacci sequence:")
    values = []
    for value in fib_tracked:
        print(f"  Yield: {value}")
        values.append(value)
    
    # Analyze the tracked events
    yield_events = [e for e in report.timeline if e.event_type == "yield_value"]
    print(f"\nYields tracked: {len(yield_events)}")
    
    gen_complete = [e for e in report.timeline if e.event_type == "generator_exhausted"]
    print(f"Generator completions: {len(gen_complete)}")
    
    print("\nTimeline:")
    for event in report.timeline:
        if event.event_type in ("yield_value", "generator_exhausted"):
            print(f"  {event.event_type}: {event.generator_name}")
            if event.yielded_value:
                print(f"    Value: {event.yielded_value}")


# =============================================================================
# EXAMPLE 2: Call Stack Analysis
# =============================================================================

def example_2_call_stack_analysis():
    """Analyze call stacks at different points in execution."""
    print("\n" + "="*70)
    print("EXAMPLE 2: CALL STACK ANALYSIS")
    print("="*70)
    
    code = """
def calculator(operation, a, b):
    if operation == "add":
        return add_nums(a, b)
    elif operation == "multiply":
        return multiply_nums(a, b)

def add_nums(x, y):
    return x + y

def multiply_nums(x, y):
    result = 1
    for _ in range(y):
        result = add_nums(result, x)
    return result

answer1 = calculator("add", 5, 3)
answer2 = calculator("multiply", 4, 3)
"""
    
    report = execute_with_debug(code)
    
    # Find all call events
    call_enter_events = [e for e in report.timeline if e.event_type == "call_enter"]
    call_exit_events = [e for e in report.timeline if e.event_type == "call_exit"]
    
    print(f"\nTotal function calls: {len(call_enter_events)}")
    print(f"Function exits: {len(call_exit_events)}")
    
    # Show call stack at each function entry
    print("\nCall stacks when functions entered:")
    for event in call_enter_events:
        if event.function_name not in ("<module>",):
            stack = report.get_call_stack_at(event.lineno)
            indent = "  " * (event.call_depth or 0)
            print(f"{indent}→ {event.function_name} (depth={event.call_depth})")
            if stack:
                print(f"{indent}  Stack: {' → '.join(stack)}")
    
    # Show the final state
    print(f"\nFinal variables: {list(report.final_state.keys())}")


# =============================================================================
# EXAMPLE 3: Async Context Monitoring
# =============================================================================

def example_3_async_context():
    """Monitor async operation contexts."""
    print("\n" + "="*70)
    print("EXAMPLE 3: ASYNC CONTEXT MONITORING")
    print("="*70)
    
    report = DebugReport("async operations")
    
    # Simulate async operations
    print("\nSimulating async operations...")
    
    with TrackedAsyncContext("fetch_data", report):
        print("  [Async] Fetching data...")
        import time
        time.sleep(0.01)  # Simulate async work
    
    with TrackedAsyncContext("process_data", report):
        print("  [Async] Processing data...")
        time.sleep(0.01)  # Simulate async work
    
    with TrackedAsyncContext("save_results", report):
        print("  [Async] Saving results...")
        time.sleep(0.01)  # Simulate async work
    
    # Analyze async events
    async_events = report.get_async_events()
    
    print(f"\nAsync events tracked: {len(async_events)}")
    
    # Group by coroutine
    async_by_name = {}
    for event in async_events:
        name = event.coroutine_name
        if name not in async_by_name:
            async_by_name[name] = []
        async_by_name[name].append(event)
    
    print("\nAsync operations timeline:")
    for name, events in sorted(async_by_name.items()):
        print(f"  {name}:")
        for event in events:
            print(f"    → {event.await_state}")


# =============================================================================
# EXAMPLE 4: Generator + Call Stack Integration
# =============================================================================

def example_4_integration():
    """Combine generator tracking with call stack analysis."""
    print("\n" + "="*70)
    print("EXAMPLE 4: GENERATOR + CALL STACK INTEGRATION")
    print("="*70)
    
    code = """
def pipeline(items):
    return (x * 2 for x in items if x > 0)

def process():
    items = [1, -2, 3, -4, 5]
    result = list(pipeline(items))
    return result

output = process()
"""
    
    report = execute_with_debug(code)
    
    # Analyze call structure
    call_events = [e for e in report.timeline if e.event_type in ("call_enter", "call_exit")]
    
    print(f"\nExecution structure:")
    for event in call_events:
        if event.event_type == "call_enter":
            print(f"  → Enter: {event.function_name} @ line {event.lineno}")
        else:
            print(f"  ← Exit: {event.function_name}")
    
    # Show final result
    print(f"\nFinal state: {report.final_state}")
    
    # Get variables by function
    print("\nVariables at function boundaries:")
    current_func = None
    for event in report.timeline:
        if event.event_type == "call_enter" and event.variables_after:
            current_func = event.function_name
            print(f"  Entering {event.function_name}:")
            for var_name in list(event.variables_after.keys())[:3]:
                print(f"    - {var_name}")


# =============================================================================
# EXAMPLE 5: Pattern Detection with Debug Report
# =============================================================================

def example_5_pattern_detection():
    """Use debug reports with pattern detection."""
    print("\n" + "="*70)
    print("EXAMPLE 5: PATTERN DETECTION")
    print("="*70)
    
    # Code with an off-by-one error
    buggy_code = """
arr = [10, 20, 30]
for i in range(len(arr) + 1):  # Off-by-one!
    value = arr[i]
"""
    
    report = execute_with_debug(buggy_code, trace_lines=False)  # Crash-only
    
    # Detect patterns
    detector = BugPatternDetector(report)
    patterns = detector.analyze()
    
    print(f"\nPatterns detected: {len(patterns)}")
    for pattern in patterns:
        print(f"\n  Pattern: {pattern.pattern_type.value}")
        print(f"  Severity: {pattern.severity}")
        print(f"  Confidence: {pattern.confidence}")
        print(f"  Description: {pattern.description}")
        if pattern.suggestion:
            print(f"  Fix suggestion: {pattern.suggestion[:100]}...")
        if pattern.fix_example:
            print(f"  Example fix provided: Yes")


# =============================================================================
# EXAMPLE 6: Variable Mutation Tracking with Generators
# =============================================================================

def example_6_mutation_tracking():
    """Track variable mutations alongside generator yields."""
    print("\n" + "="*70)
    print("EXAMPLE 6: VARIABLE MUTATION TRACKING WITH GENERATORS")
    print("="*70)
    
    def accumulator(values):
        """Generator that accumulates values."""
        total = 0
        for val in values:
            total += val
            yield total
    
    report = DebugReport("accumulator test")
    
    # Track the generator
    acc = track_generator(
        accumulator([1, 2, 3, 4]),
        name="accumulator",
        report=report
    )
    
    print("\nAccumulating values:")
    for result in acc:
        print(f"  Accumulated: {result}")
    
    # Show what was captured
    yield_events = [e for e in report.timeline if e.event_type == "yield_value"]
    
    print(f"\nYields captured: {len(yield_events)}")
    for i, event in enumerate(yield_events, 1):
        print(f"  Yield {i}: {event.yielded_value}")


# =============================================================================
# EXAMPLE 7: Deep Call Stack with Multiple Nesting Levels
# =============================================================================

def example_7_deep_nesting():
    """Analyze deeply nested function calls."""
    print("\n" + "="*70)
    print("EXAMPLE 7: DEEP CALL STACK ANALYSIS")
    print("="*70)
    
    code = """
def level1():
    return level2()

def level2():
    return level3()

def level3():
    return level4()

def level4():
    x = 42
    return x

result = level1()
"""
    
    report = execute_with_debug(code)
    
    # Find the deepest point
    max_depth = 0
    deepest_event = None
    
    for event in report.timeline:
        if event.event_type == "call_enter" and event.call_depth:
            if event.call_depth > max_depth:
                max_depth = event.call_depth
                deepest_event = event
    
    if deepest_event:
        print(f"\nMax call depth: {deepest_event.call_depth}")
        print(f"Deepest function: {deepest_event.function_name}")
        
        stack = report.get_call_stack_at(deepest_event.lineno)
        if stack:
            print(f"Call stack at deepest point:")
            for i, func in enumerate(stack, 1):
                print(f"  {i}. {func}")


# =============================================================================
# MAIN: Run all examples
# =============================================================================

def main():
    """Run all examples."""
    print("\n" + "#"*70)
    print("# PYTHON-DEBUG v12.2 COMPREHENSIVE EXAMPLES")
    print("#"*70)
    
    try:
        example_1_generator_tracking()
        example_2_call_stack_analysis()
        example_3_async_context()
        example_4_integration()
        example_5_pattern_detection()
        example_6_mutation_tracking()
        example_7_deep_nesting()
        
        print("\n" + "#"*70)
        print("# ALL EXAMPLES COMPLETED SUCCESSFULLY")
        print("#"*70 + "\n")
        
    except Exception as e:
        print(f"\n✗ Example failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
