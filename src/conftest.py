"""
Root pytest configuration for verification-debugging-suite.

Provides:
- Centralized custom marker registration
- Shared fixtures for timing, memory, and scenario building
- Cross-component test utilities
"""

import pytest
import time
import sys


# ============================================================================
# CENTRALIZED MARKER REGISTRATION
# ============================================================================
# All markers are now defined here and in pytest.ini (for redundancy/IDE support)

def pytest_configure(config):
    """Register pytest markers (centralized, single source of truth)."""
    markers = [
        ("tracing", "Execution tracing tests"),
        ("patterns", "Bug pattern detection tests"),
        ("verification", "Formal verification tests"),
        ("generation", "Test generation tests"),
        ("contract", "Contract-based verification tests"),
        ("integration", "Integration tests combining multiple features"),
        ("performance", "Performance/benchmark tests"),
        ("slow", "Long-running tests (excluded by default)"),
    ]
    for marker_name, marker_desc in markers:
        config.addinivalue_line("markers", f"{marker_name}: {marker_desc}")


# ============================================================================
# SHARED FIXTURES
# ============================================================================

@pytest.fixture
def execution_timer():
    """Measure execution time of any operation."""
    class ExecutionTimer:
        def __init__(self):
            self.measurements = {}

        def measure(self, operation_name, callable_obj, *args, **kwargs):
            """Time a callable operation."""
            start = time.perf_counter()
            result = callable_obj(*args, **kwargs)
            elapsed = time.perf_counter() - start
            self.measurements[operation_name] = elapsed
            return result, elapsed

        def get_summary(self):
            """Get all measurements."""
            return self.measurements

    return ExecutionTimer()


@pytest.fixture
def code_scenarios():
    """Reusable code samples for testing across all components."""
    return {
        "divide_by_zero": "def divide(a, b):\n    return a / b",
        "null_dereference": "def process(data):\n    return data[0]",
        "off_by_one": "def loop_error():\n    for i in range(10):\n        x = i\n    return x",
        "type_error": "def type_mismatch(x):\n    return x + 'string'",
        "uninitialized": "def use_var():\n    if False:\n        y = 5\n    return y",
        "simple_add": "def add(a, b):\n    return a + b",
        "safe_divide": "def safe_divide(a, b):\n    if b == 0:\n        return None\n    return a / b",
    }


@pytest.fixture
def memory_tracker():
    """Track memory snapshots for memory usage analysis."""
    import sys as sys_module

    class MemoryTracker:
        def __init__(self):
            self.snapshots = []

        def snapshot(self, label, obj):
            """Record memory size of an object."""
            size = sys_module.getsizeof(obj)
            self.snapshots.append({"label": label, "bytes": size})
            return size

        def get_summary(self):
            """Get all snapshots."""
            return self.snapshots

    return MemoryTracker()
