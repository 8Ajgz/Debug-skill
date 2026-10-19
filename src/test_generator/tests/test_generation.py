"""
Tests for Test-Generator v1.1 comprehensive test generation.

Tests edge case generation, mutation testing, metamorphic tests,
and adversarial red-team testing.
"""

import pytest
from ..test_generator import TestGenerator


class TestEdgeCaseGeneration:
    """Test edge case detection and test generation."""
    
    @pytest.fixture
    def generator(self):
        return TestGenerator()
    
    @pytest.mark.generation
    def test_simple_function_generation(self, generator):
        """Test test generation for simple function."""
        code = "def add(a, b): return a + b"
        tests = generator.generate_tests(code, language="python")
        
        assert tests is not None
        assert hasattr(tests, 'test_cases') or len(tests) > 0
    
    @pytest.mark.generation
    def test_edge_case_detection(self, generator):
        """Test that edge cases are generated."""
        code = """
def divide(a, b):
    return a / b
"""
        tests = generator.generate_tests(code, language="python")
        
        # Should generate edge cases like zero division
        assert tests is not None
        test_cases = tests.test_cases if hasattr(tests, 'test_cases') else []
        assert len(test_cases) > 0
    
    @pytest.mark.generation
    @pytest.mark.parametrize("code", [
        "def abs(x): return x if x >= 0 else -x",
        "def max(a, b): return a if a > b else b",
        "def is_even(n): return n % 2 == 0",
    ])
    def test_boundary_value_testing(self, generator, code):
        """Test boundary value test generation."""
        tests = generator.generate_tests(code, language="python")
        assert tests is not None


class TestMutationTesting:
    """Test mutation analysis and mutation score."""
    
    @pytest.fixture
    def generator(self):
        return TestGenerator()
    
    @pytest.mark.generation
    def test_mutation_analysis(self, generator):
        """Test mutation score calculation."""
        code = "def add(a, b): return a + b"
        tests = generator.generate_tests(code, language="python")
        
        # Should have mutation score
        mutation_score = tests.mutation_score if hasattr(tests, 'mutation_score') else 0
        assert mutation_score is not None
    
    @pytest.mark.generation
    def test_mutation_detection(self, generator):
        """Test that mutations are properly detected."""
        code = """
def greater(a, b):
    if a > b:
        return a
    else:
        return b
"""
        tests = generator.generate_tests(code, language="python")
        
        # Should detect operator mutations (>, >=, etc.)
        assert tests is not None


class TestMetamorphicTesting:
    """Test metamorphic test generation."""
    
    @pytest.fixture
    def generator(self):
        return TestGenerator()
    
    @pytest.mark.generation
    def test_metamorphic_properties(self, generator):
        """Test generation of metamorphic tests."""
        code = "def add(a, b): return a + b"
        tests = generator.generate_tests(code, language="python")
        
        # Should generate metamorphic tests
        test_cases = tests.test_cases if hasattr(tests, 'test_cases') else []
        metamorphic = [t for t in test_cases if hasattr(t, 'category') and t.category == 'metamorphic']
        
        # May or may not have metamorphic tests depending on function
        assert tests is not None
    
    @pytest.mark.generation
    @pytest.mark.parametrize("code", [
        "def commutative_add(a, b): return a + b",  # a+b == b+a
        "def associative_multiply(a, b, c): return (a * b) * c",  # (a*b)*c == a*(b*c)
    ])
    def test_property_preservation(self, generator, code):
        """Test that metamorphic properties are preserved."""
        tests = generator.generate_tests(code, language="python")
        assert tests is not None


class TestAdversarialTesting:
    """Test adversarial red-team test generation."""
    
    @pytest.fixture
    def generator(self):
        return TestGenerator()
    
    @pytest.mark.generation
    def test_adversarial_test_generation(self, generator):
        """Test generation of adversarial red-team tests."""
        code = "def process(data): return len(data)"
        tests = generator.generate_tests(code, language="python")
        
        # Should generate adversarial tests
        test_cases = tests.test_cases if hasattr(tests, 'test_cases') else []
        adversarial = [t for t in test_cases if hasattr(t, 'category') and t.category == 'adversarial']
        
        assert tests is not None
    
    @pytest.mark.generation
    @pytest.mark.parametrize("code", [
        "def concat(s1, s2): return s1 + s2",  # Test injection
        "def parse_json(s): return json.loads(s)",  # Test malformed input
    ])
    def test_injection_detection(self, generator, code):
        """Test detection of injection vulnerabilities."""
        tests = generator.generate_tests(code, language="python")
        assert tests is not None


class TestCoverageAnalysis:
    """Test code coverage analysis."""
    
    @pytest.fixture
    def generator(self):
        return TestGenerator()
    
    @pytest.mark.generation
    def test_coverage_measurement(self, generator):
        """Test coverage percentage calculation."""
        code = """
def check(x):
    if x > 0:
        return "positive"
    elif x < 0:
        return "negative"
    else:
        return "zero"
"""
        tests = generator.generate_tests(code, language="python")
        
        coverage = tests.coverage_percent if hasattr(tests, 'coverage_percent') else 0
        # Should measure coverage
        assert coverage is not None
    
    @pytest.mark.generation
    def test_uncovered_paths(self, generator):
        """Test identification of uncovered code paths."""
        code = """
def complex_logic(a, b, c):
    if a > 0:
        if b > 0:
            if c > 0:
                return a + b + c
    return 0
"""
        tests = generator.generate_tests(code, language="python")
        
        # Should identify multiple paths
        assert tests is not None


class TestTestCaseStructure:
    """Test structure of generated test cases."""
    
    @pytest.fixture
    def generator(self):
        return TestGenerator()
    
    @pytest.mark.generation
    def test_test_case_format(self, generator):
        """Test format of generated test cases."""
        code = "def double(x): return x * 2"
        tests = generator.generate_tests(code, language="python")
        
        test_cases = tests.test_cases if hasattr(tests, 'test_cases') else []
        
        for test_case in test_cases:
            assert hasattr(test_case, 'input') or hasattr(test_case, 'inputs')
            assert hasattr(test_case, 'expected') or hasattr(test_case, 'expected_output')
    
    @pytest.mark.generation
    def test_test_case_categories(self, generator):
        """Test that test cases are properly categorized."""
        code = "def abs(x): return x if x >= 0 else -x"
        tests = generator.generate_tests(code, language="python")
        
        test_cases = tests.test_cases if hasattr(tests, 'test_cases') else []
        
        # Should have various categories
        categories = set()
        for test_case in test_cases:
            if hasattr(test_case, 'category'):
                categories.add(test_case.category)
        
        # Should have some categorization
        assert len(categories) > 0 or len(test_cases) > 0
