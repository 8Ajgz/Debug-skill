# Changelog

## [1.1.0] - 2026-06-24

### Added

- **Consolidation & Standardization:**
  - Added root `src/conftest.py` with centralized pytest fixtures and marker registration
  - Generated `API.md` (auto-generated API reference from docstrings)
  - Generated `INTEROP.yaml` (operation metadata, schemas, token costs)
  - Generated `openapi.yaml` (OpenAPI 3.0 specification, 12 operations)
  - Generated `MANIFEST.txt` (feature completeness checklist)
  - Added `.gitignore` to exclude bytecode and auto-generated files

### Changed

- **Documentation Consolidation:**
  - README.md reduced from 71 to 20 lines (references SKILL.md instead of duplicating)
  - SKILL.md condensed from 475 to 413 lines (removed verbose workflow examples)
  - Moved detailed examples to reference section with links to docs/
  - All use-case guidance now centralized in SKILL.md "When to Use Each Component"

- **Test Infrastructure:**
  - Simplified `src/python_debug/conftest.py` (removed duplicate marker registration)
  - Marker registration now centralized in root `src/conftest.py`
  - Shared fixtures (execution_timer, code_scenarios, memory_tracker) available to all tests

- **Standardize-Skill Compliance:**
  - SKILL.md now 413 lines (87-line buffer before 500-line limit)
  - Full standardize-skill compliance: code quality ✅, documentation ✅, testing ✅
  - Ready for skill builder tool usage

### Removed

- Deleted old example files:
  - `src/python_debug/EXAMPLES_v12.0_COMPLETE.py` (11.4KB)
  - `src/python_debug/EXAMPLES_v12_2.py` (11.5KB)
- Removed bytecode from distribution (~250KB `__pycache__` directories)

### Sizes

- **SKILL.md:** 475 → 413 lines (62-line reduction, 87-line expansion buffer)
- **README.md:** 71 → 20 lines (51-line reduction)
- **Package:** ~228KB reduction from consolidated examples + bytecode cleanup
- **Total consolidation:** 800+ lines of redundant code eliminated

### Breaking Changes

- **None.** All consolidation changes are backward compatible.
- Python imports unchanged
- API unchanged
- Test suite 100% compatible

### Migration Path

- No user action required
- Existing code using verification-debugging-suite works without changes
- Type consolidation (Phase 2) deferred to v1.2+ (if planned)

---

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

---

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

---

## [0.5.0] - 2026-06-22

### Initial
- Suite skeleton with partial components
- python-debug, code-orchestrator, test-generator functional
- master-debugger-v5, pyprover, troubleshooting stubs only
