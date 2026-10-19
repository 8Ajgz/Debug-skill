#!/usr/bin/env python3
"""
Timeline Analyzer for python-debug v12.3

Analyzes and visualizes:
- Event distribution by type
- Memory usage over execution
- Execution timeline visualization
- Performance hotspots
- Pattern detection efficiency

Usage:
    python3 scripts/analyze_timeline.py
"""

import sys
import os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from debug_report import execute_with_debug
from bug_patterns import BugPatternDetector


class TimelineAnalyzer:
    """Analyze execution timelines for insights."""
    
    def __init__(self, report):
        self.report = report
        self.timeline = report.timeline
    
    def event_distribution(self):
        """Show distribution of event types."""
        if not self.timeline:
            return {}
        
        event_types = [e.event_type for e in self.timeline]
        distribution = Counter(event_types)
        
        print("\nEvent Distribution:")
        print("-" * 50)
        
        total = len(self.timeline)
        for event_type, count in sorted(distribution.items(), key=lambda x: -x[1]):
            percentage = (count / total * 100) if total > 0 else 0
            bar = "█" * int(percentage / 5)
            print(f"  {event_type:20s}: {count:4d} ({percentage:5.1f}%) {bar}")
        
        return distribution
    
    def timeline_memory_analysis(self):
        """Analyze memory characteristics of timeline."""
        if not self.timeline:
            return {}
        
        print("\nMemory Analysis:")
        print("-" * 50)
        
        # Total timeline size
        total_size = sum(sys.getsizeof(e) for e in self.timeline)
        print(f"  Timeline events:  {len(self.timeline)} events")
        print(f"  Total size:       {total_size / 1024:.2f} KB")
        print(f"  Average per event: {total_size / len(self.timeline):.0f} bytes")
        
        # Final state size
        final_state_size = sum(
            sys.getsizeof(k) + sys.getsizeof(v)
            for k, v in self.report.final_state.items()
        )
        print(f"  Final state:      {final_state_size / 1024:.2f} KB")
        print(f"  Total report:     {(total_size + final_state_size) / 1024:.2f} KB")
        
        # Variables in final state
        print(f"  Variables:        {len(self.report.final_state)}")
        
        return {
            'timeline_kb': total_size / 1024,
            'final_state_kb': final_state_size / 1024,
            'events': len(self.timeline)
        }
    
    def execution_timeline(self):
        """Print execution timeline with timestamps."""
        if not self.timeline:
            return
        
        print("\nExecution Timeline:")
        print("-" * 70)
        print(f"{'Line':>4} {'Type':15s} {'Code':35s} {'Time (ms)':>10s}")
        print("-" * 70)
        
        start_time = self.timeline[0].timestamp_ms if self.timeline else 0
        
        for i, event in enumerate(self.timeline[:20]):  # First 20 events
            elapsed = event.timestamp_ms - start_time
            code = (event.code or "")[:33]
            line = event.lineno or 0
            
            print(f"{line:4d} {event.event_type:15s} {code:35s} {elapsed:10.2f}")
        
        if len(self.timeline) > 20:
            print(f"... and {len(self.timeline) - 20} more events")
    
    def variable_mutations(self):
        """Analyze variable mutations."""
        print("\nVariable Mutations:")
        print("-" * 50)
        
        all_vars = set()
        for event in self.timeline:
            if event.event_type == "line" and event.variables_after:
                all_vars.update(event.variables_after.keys())
        
        if not all_vars:
            print("  No mutations tracked")
            return {}
        
        mutations = {}
        for var in sorted(all_vars):
            var_mutations = self.report.get_variable_mutations(var)
            if var_mutations:
                mutations[var] = len(var_mutations)
                print(f"  {var:15s}: {len(var_mutations):2d} mutations")
        
        return mutations
    
    def aliasing_analysis(self):
        """Analyze object aliasing."""
        aliases = self.report.get_true_aliases()
        
        print("\nObject Aliasing:")
        print("-" * 50)
        
        if not aliases:
            print("  No aliases detected")
            return {}
        
        for obj_id, vars_list in sorted(aliases.items()):
            if len(vars_list) > 1:
                print(f"  Object {obj_id}: {', '.join(vars_list)}")
        
        return aliases
    
    def exception_info(self):
        """Show exception information if present."""
        if not self.report.exception_info:
            print("\nNo exceptions")
            return
        
        print("\nException Info:")
        print("-" * 50)
        
        exc = self.report.exception_info
        print(f"  Exception: {exc.get('exception', 'Unknown')}")
        print(f"  Line:      {exc.get('line_no', 'Unknown')}")
        print(f"  Message:   {exc.get('message', 'None')}")
    
    def pattern_analysis(self):
        """Analyze detected patterns."""
        detector = BugPatternDetector(self.report)
        patterns = detector.analyze()
        
        print("\nPattern Detection:")
        print("-" * 50)
        
        if not patterns:
            print("  No patterns detected")
            return {}
        
        for pattern in patterns:
            severity = getattr(pattern, 'severity', 'UNKNOWN')
            print(f"  [{severity:6s}] {pattern.pattern_type}")
            if hasattr(pattern, 'description'):
                print(f"           {pattern.description}")
        
        return {'count': len(patterns)}
    
    def efficiency_metrics(self):
        """Calculate efficiency metrics."""
        print("\nEfficiency Metrics:")
        print("-" * 50)
        
        if not self.timeline:
            return {}
        
        # Lines of code (rough estimate)
        lines_code = len(set(e.lineno for e in self.timeline if e.lineno))
        
        # Events per line
        events_per_line = len(self.timeline) / lines_code if lines_code > 0 else 0
        
        # Exception per line (if crashed)
        has_exception = self.report.exception_info is not None
        
        # Total execution time
        if len(self.timeline) > 1:
            exec_time = self.timeline[-1].timestamp_ms - self.timeline[0].timestamp_ms
        else:
            exec_time = 0
        
        print(f"  Lines executed:     {lines_code}")
        print(f"  Events generated:   {len(self.timeline)}")
        print(f"  Events per line:    {events_per_line:.1f}")
        print(f"  Total time:         {exec_time:.2f}ms")
        print(f"  Execution status:   {'CRASHED' if has_exception else 'SUCCESS'}")
        
        return {
            'lines': lines_code,
            'events': len(self.timeline),
            'events_per_line': events_per_line,
            'time_ms': exec_time,
        }
    
    def print_full_analysis(self):
        """Print comprehensive analysis."""
        print("\n" + "="*70)
        print("TIMELINE ANALYSIS")
        print("="*70)
        
        self.event_distribution()
        self.timeline_memory_analysis()
        self.execution_timeline()
        self.variable_mutations()
        self.aliasing_analysis()
        self.exception_info()
        self.pattern_analysis()
        metrics = self.efficiency_metrics()
        
        return metrics


def analyze_code(code, description=""):
    """Analyze a piece of code."""
    if description:
        print(f"\n{'#'*70}")
        print(f"# {description}")
        print(f"{'#'*70}")
    
    report = execute_with_debug(code)
    analyzer = TimelineAnalyzer(report)
    return analyzer.print_full_analysis()


if __name__ == "__main__":
    # Example analyses
    print("PYTHON-DEBUG TIMELINE ANALYZER")
    print("="*70)
    
    # Scenario 1: Simple code
    analyze_code("""
x = 1
y = 2
z = x + y
""", "Scenario 1: Simple Assignment")
    
    # Scenario 2: Off-by-one bug
    analyze_code("""
arr = [1, 2, 3]
for i in range(1, len(arr) + 1):
    x = arr[i]
""", "Scenario 2: Off-by-One Loop (Crashes)")
    
    # Scenario 3: Complex with generator
    analyze_code("""
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

gen = fibonacci(5)
result = list(gen)
""", "Scenario 3: Generator Execution")
    
    # Scenario 4: Aliasing
    analyze_code("""
x = [1, 2, 3]
y = x
z = x
y.append(4)
""", "Scenario 4: Object Aliasing")
    
    print("\n" + "="*70)
    print("Analysis complete!")
