# Changelog

## [1.0.1] - 2026-06-24

### Fixed
- **CRITICAL: Fixed circular import issue in master_debugger/phases.py**
  - Lines 70, 71, 104, 127: Converted absolute imports to relative imports
  - Enables Phase 1 (RuntimeDebug), Phase 2 (FormalVerification), Phase 3 (DesignReview)
  - Impact: Master-debugger-v5 orchestrator now fully functional

- **CRITICAL: Fixed import errors in python_debug/conftest.py**
  - Lines 19, 111, 268: Converted absolute imports to relative imports
  - Enables pytest collection and test fixture loading
  - Impact: pytest now discovers and runs 80+ tests

### Added
- **Comprehensive Test Suite (80+ tests)**
  - `src/master_debugger/tests/test_orchestration.py` (10+ tests)
  - `src/python_debug/tests/test_execution_tracing.py` (25+ tests)
  - `src/pyprover/tests/test_verification.py` (15+ tests)
  - `src/test_generator/tests/test_generation.py` (20+ tests)
  - `src/tests/test_integration.py` (10+ tests)

- **Test Infrastructure**
  - pytest.ini configuration with custom markers
  - Parametrized edge case testing
  - Contract-based formal verification tests
  - Integration tests for end-to-end workflows

- **Documentation Updates**
  - Updated SKILL.md with test suite section
  - Test running instructions and examples
  - Test coverage matrix by component
  - Test marker reference guide

## [1.0.0] - 2026-06-24

### Added
- Master-Debugger-v5: Complete 4-phase orchestrator
  - Phase 0: Static analysis (mypy, pylint, bandit)
  - Phase 1: Runtime debugging (python-debug)
  - Phase 2: Formal verification (pyprover)
  - Phase 3: Design review (troubleshooting)
- PyProver Phase 2: Contract verification with Z3 solver
- Troubleshooting: Full 5-phase methodology implementation
- Root SKILL.md documentation
- Comprehensive API documentation
- Production package metadata

### Changed
- Merged all 7 component skills into unified suite
- Standardized all type hints and error handling
- Updated all documentation to reflect complete implementation

### Fixed
- Master-debugger-v5 was stub (2.5KB) → now full orchestrator
- PyProver was Phase 3 only → now includes Phase 2
- Troubleshooting was minimal stub → now full 5-phase
- Missing root documentation → now comprehensive SKILL.md
- Missing packaging metadata → now setup.py, skill.json

## [0.5.0] - 2026-06-22

### Initial
- Suite skeleton with partial components
- python-debug, code-orchestrator, test-generator functional
- master-debugger-v5, pyprover, troubleshooting stubs only
