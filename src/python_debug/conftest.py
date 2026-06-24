"""
pytest configuration for python-debug v12.3

Provides:
- Execution timing fixtures
- Debug scenario fixtures
- Custom markers for test categorization
- Performance regression tracking
"""

import pytest
import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from debug_report import execute_with_debug, DebugReport


# ============================================================================
# CUSTOM MARKERS
# ============================================================================

def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "tracing: tests for execution tracing functionality"
    )
    config.addinivalue_line(
        "markers", "patterns: tests for bug pattern detection"
    )
    config.addinivalue_line(
        "markers", "performance: performance/benchmark tests"
    )
    config.addinivalue_line(
        "markers", "integration: integration tests combining multiple features"
    )


# ============================================================================
# FIXTURES: Timing & Performance
# ============================================================================

@pytest.fixture
def trace_execution_time():
    """Measure execution time of debug tracing."""
    class ExecutionTimer:
        def __init__(self):
            self.timings = {}
        
        def measure(self, name, code, **kwargs):
            """Measure time to execute code with debugging."""
            start = time.perf_counter()
            report = execute_with_debug(code, **kwargs)
            elapsed = time.perf_counter() - start
            self.timings[name] = elapsed
            return report, elapsed
        
        def get_report(self):
            """Get timing summary."""
            return self.timings
    
    return ExecutionTimer()


@pytest.fixture
def timeline_memory_tracker():
    """Track memory growth of timeline during execution."""
    import sys
    
    class MemoryTracker:
        def __init__(self):
            self.snapshots = []
        
        def measure(self, name, code, **kwargs):
            """Measure timeline memory growth."""
            report = execute_with_debug(code, **kwargs)
            
            # Measure timeline size
            timeline_size = sys.getsizeof(report.timeline)
            for event in report.timeline:
                timeline_size += sys.getsizeof(event)
            
            # Measure final state size
            final_state_size = sys.getsizeof(report.final_state)
            for k, v in report.final_state.items():
                final_state_size += sys.getsizeof(k) + sys.getsizeof(v)
            
            self.snapshots.append({
                'name': name,
                'timeline_bytes': timeline_size,
                'final_state_bytes': final_state_size,
                'total_bytes': timeline_size + final_state_size,
                'event_count': len(report.timeline)
            })
            
            return report
        
        def get_summary(self):
            """Get memory summary."""
            return self.snapshots
    
    return MemoryTracker()


@pytest.fixture
def pattern_detection_timer():
    """Measure pattern detection performance."""
    from bug_patterns import BugPatternDetector
    
    class PatternTimer:
        def __init__(self):
            self.timings = {}
        
        def measure(self, name, code, **kwargs):
            """Measure time to detect patterns."""
            report = execute_with_debug(code, **kwargs)
            
            start = time.perf_counter()
            detector = BugPatternDetector(report)
            patterns = detector.analyze()
            elapsed = time.perf_counter() - start
            
            self.timings[name] = {
                'time_ms': elapsed * 1000,
                'pattern_count': len(patterns),
                'patterns': [p.pattern_type for p in patterns]
            }
            
            return report, patterns, elapsed
        
        def get_report(self):
            return self.timings
    
    return PatternTimer()


# ============================================================================
# FIXTURES: Debug Scenarios
# ============================================================================

@pytest.fixture
def simple_code_scenario():
    """Simple, fast execution scenario."""
    return """
x = 1
y = 2
z = x + y
"""


@pytest.fixture
def complex_code_scenario():
    """Complex scenario with multiple features."""
    return """
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

gen = fibonacci(5)
result = list(gen)
"""


@pytest.fixture
def aliasing_scenario():
    """Scenario with object aliasing."""
    return """
x = [1, 2, 3]
y = x
z = [1, 2, 3]
x.append(4)
y.append(5)
"""


@pytest.fixture
def crash_scenario():
    """Scenario that crashes intentionally."""
    return """
arr = [1, 2, 3]
for i in range(1, len(arr) + 1):
    x = arr[i]
"""


@pytest.fixture
def fixture_injection_scenario():
    """Scenario requiring fixture injection."""
    class BrokenRepr:
        def __repr__(self):
            raise RuntimeError("broken")
        def get_value(self):
            return 42
    
    return {
        'code': """
result = OBJ.get_value()
y = result * 2
""",
        'fixtures': {'OBJ': BrokenRepr()}
    }


# ============================================================================
# FIXTURES: Report Analysis
# ============================================================================

@pytest.fixture
def report_analyzer():
    """Analyze report contents and structure."""
    class ReportAnalyzer:
        def __init__(self):
            self.reports = {}
        
        def analyze(self, name, report):
            """Analyze a debug report."""
            self.reports[name] = {
                'execution_complete': report.execution_complete,
                'timeline_length': len(report.timeline),
                'exception': report.exception_info is not None,
                'final_state_vars': list(report.final_state.keys()),
                'aliases': report.get_true_aliases(),
            }
            return self.reports[name]
        
        def compare(self, name1, name2):
            """Compare two reports."""
            if name1 not in self.reports or name2 not in self.reports:
                return None
            
            r1 = self.reports[name1]
            r2 = self.reports[name2]
            
            return {
                'timeline_diff': r2['timeline_length'] - r1['timeline_length'],
                'exception_diff': r2['exception'] != r1['exception'],
                'vars_diff': set(r2['final_state_vars']) - set(r1['final_state_vars']),
            }
    
    return ReportAnalyzer()


# ============================================================================
# HELPER: Assertion Helpers
# ============================================================================

class DebugAssertions:
    """Custom assertions for debug reports."""
    
    @staticmethod
    def assert_traces_correctly(report, expected_vars=None):
        """Assert that tracing executed correctly."""
        assert report.execution_complete, "Report should be complete"
        assert len(report.timeline) > 0, "Timeline should have events"
        
        if expected_vars:
            for var in expected_vars:
                assert var in report.final_state, f"Variable {var} should be in final state"
    
    @staticmethod
    def assert_detects_pattern(report, expected_pattern):
        """Assert that a specific pattern is detected."""
        from bug_patterns import BugPatternDetector
        
        detector = BugPatternDetector(report)
        patterns = detector.analyze()
        pattern_types = [p.pattern_type for p in patterns]
        
        pattern_str = str(expected_pattern).upper().replace('BUGPATTERNTYPE.', '')
        
        found = any(pattern_str in str(pt).upper() for pt in pattern_types)
        assert found, f"Expected pattern {expected_pattern} not found. Got: {pattern_types}"
    
    @staticmethod
    def assert_has_aliases(report, expected_vars=None):
        """Assert that aliasing is detected."""
        aliases = report.get_true_aliases()
        
        assert len(aliases) > 0, "Should detect aliases"
        
        if expected_vars:
            found = False
            for obj_id, vars_list in aliases.items():
                if all(v in vars_list for v in expected_vars):
                    found = True
                    break
            assert found, f"Expected alias group {expected_vars} not found"
    
    @staticmethod
    def assert_execution_time(elapsed_ms, max_ms):
        """Assert execution time is within threshold."""
        assert elapsed_ms <= max_ms, \
            f"Execution took {elapsed_ms:.2f}ms, expected <= {max_ms}ms"


@pytest.fixture
def debug_assertions():
    """Provide custom assertion helpers."""
    return DebugAssertions()


# ============================================================================
# HOOK: Performance Regression Detection
# ============================================================================

def pytest_runtest_makereport(item, call):
    """Capture performance data for regression detection."""
    if "performance" in item.keywords:
        # This is a performance test - hook it for regression tracking
        pass


if __name__ == "__main__":
    print("pytest configuration loaded for python-debug")
    print("Available fixtures:")
    print("  - trace_execution_time: Measure tracing overhead")
    print("  - timeline_memory_tracker: Track timeline memory growth")
    print("  - pattern_detection_timer: Measure pattern detection speed")
    print("  - simple_code_scenario, complex_code_scenario, etc.")
    print("  - debug_assertions: Custom assertion helpers")
