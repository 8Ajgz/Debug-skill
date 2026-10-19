"""Test Generator v1.1 - Test generation with mutation and metamorphic tests"""
try:
    from .test_generator import TestGenerator
    __all__ = ['TestGenerator']
except ImportError:
    __all__ = []

__version__ = "1.1"
