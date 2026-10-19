"""Python Debug v12.3 - Runtime execution tracing and bug pattern detection"""
try:
    from .debug_report import execute_with_debug, DebugReport
    from .bug_patterns import BugPatternDetector
    __all__ = ['execute_with_debug', 'DebugReport', 'BugPatternDetector']
except ImportError:
    __all__ = []

__version__ = "12.3"
