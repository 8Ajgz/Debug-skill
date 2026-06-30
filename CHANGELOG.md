# Changelog

## [2.2.0] - 2026-06-30

### Added

- **C/C++-Debug (Phase 4 of the multi-language roadmap):**
  - `src/cpp_debug/diagnostics.py` - compiles C/C++ with `clang -fsyntax-only -Wall -Wextra` and parses warnings/errors
  - `src/cpp_debug/analyzer.py` - drives the Clang Static Analyzer (`clang --analyze`) for path-sensitive bugs (null deref, memory leaks, div-by-zero)
  - `src/cpp_debug/classifier.py` - classifies raw diagnostics/findings into unified `BugPattern` objects, deduped + severity-sorted
  - `src/cpp_debug/phases.py` - `CppDebugger` orchestrating diagnostics + analyzer + a design-review pass (unsafe string APIs, unmatched raw `new`)
  - `src/cpp_debug/setup.py` - `claude_check_and_install()` for the clang/clang++ toolchain, mirroring `rust_debug/setup.py`
  - 19 new tests in `src/cpp_debug/tests/test_cpp_debug_phase4.py`, all passing against a real clang 18 install
  - `master_debugger/orchestrator.py` now routes `language="c"|"cpp"|"c++"` to `CppDebugger` automatically
  - Added `LanguageType.C` and `ComponentType.{RUST_DEBUG,CPP_DEBUG}` to `common/interop.py`

### Fixed (suite-wide cleanup pass - 20 failing tests → 0)

- `src/__init__.py` was missing entirely, breaking every `from ..x import y` relative import across the package
- 4 test directories (`master_debugger/tests`, `pyprover/tests`, `python_debug/tests`, `test_generator/tests`) were missing `__init__.py`, breaking relative imports under pytest
- `master_debugger/__init__.py` exported the legacy v5 orchestrator only; the documented v6/PyProver/Rust-aware `MasterDebugger` in `orchestrator.py` was never wired into the package's static/runtime/design phases - it appended phase labels without running any real analysis. Now delegates to the real `Phase0StaticAnalysis`/`Phase1RuntimeDebug`/`Phase3DesignReview` for Python.
- `orchestrator_v5.py`'s `classify_risk()` had an overly broad CRITICAL keyword bucket (`open(`, `secret`, `validate`, generic `api`) that false-positived plain file reads as CRITICAL; narrowed to genuinely security/network-sensitive keywords and moved `open(` to its own HIGH-risk check
- Added missing `RiskLevel.LOW` to `master_debugger/types.py`
- `PyProverBridge.verify()` was a stub that ignored its input entirely; implemented real `_convert_to_unified_report()` and `_map_language_type()` methods (previously referenced only by tests, never defined) and removed a dead, broken `_create_placeholder_report()` that constructed `UnifiedDebugReport` with nonexistent kwargs
- Extended `LanguageType` enum from 7 to 11 members (added `C`, `CSHARP`, `WASM`, `ASSEMBLY`) to match the suite's documented "12 PyProver languages" claim
- Added missing `summary: str` field to `UnifiedDebugReport` dataclass (referenced by tests, never defined)
- `rust_debug/borrow_checker.py` and `clippy_linter.py` referenced nonexistent enum members `ComponentType.RUNTIME` / `ComponentType.STATIC` and a nonexistent `.line` attribute on `BugPattern` (real field is `.location`); fixed both, added `ComponentType.RUST_DEBUG`
- `rust_debug/phases.py` constructed `UnifiedDebugReport()` with no arguments despite `component`/`language`/`code` being required fields
- `tests/test_rust_debug_phases_2_3.py` constructed `BugPattern(message=..., line=...)` using field names that don't exist on the real dataclass (`description`/`location` do); fixed 4 call sites
- `src/javascript_debug/tests/test_execution_tracing.py` imported from a stale package name (`verification_debugging_suite`) left over from before the project was renamed
- `src/tests/test_integration.py` asserted `risk_level.value == 'CRITICAL'` against an enum whose value convention is lowercase (`'critical'`) everywhere else in the codebase
- `MASTER_DEBUGGER` component label updated from stale `"master-debugger-v5"` to `"master-debugger-v6"`
- SKILL.md was missing version-history entries for v2.0/v2.1 despite the frontmatter version having moved past v1.2; added retroactive entries plus Rust-Debug/Cpp-Debug component docs (the Rust-Debug section was entirely absent from SKILL.md despite being v2.1's headline feature)

### Test Suite

- Full suite: **144/144 passing** (`python -m pytest tests/ src/ -q`), up from 105 passing / 20 failing before this pass

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
