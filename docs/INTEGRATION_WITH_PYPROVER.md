# PyProver Integration with Debug-Suite v2.0

**Version:** 2.0.0  
**Integration Date:** June 28, 2026  
**PyProver Version:** v12.0+

---

## Overview

Debug-Suite v2.0 integrates with **PyProver v12** to enable formal verification across **12 programming languages**. The integration is optional and graceful: if PyProver is not installed, debug-suite continues with local analysis only.

### What is PyProver?

PyProver is a formal verification framework that uses the Z3 SMT solver to prove code correct for **all possible inputs**. It automatically detects 10 universal proof templates (ACCUMULATOR, BINARY_SEARCH, RECURSION, etc.) and generates formal proofs that code is correct.

### Integration Strategy

Rather than reimplementing language support from scratch, debug-suite v2.0 **leverages PyProver's infrastructure**:

- **PyProver provides:** Language adapters, contract parsing, template detection, Z3 verification
- **Debug-Suite adds:** Runtime debugging, execution tracing, bug pattern detection, property-based testing

**Result:** Complementary strengths. PyProver proves "is this correct for all inputs?" while Debug-Suite answers "what bugs exist in practice?"

---

## Supported Languages

Through PyProver integration, debug-suite now supports **12 languages**:

| Language | Status | Debug-Suite Layer | Debugger |
|----------|--------|------|---|
| **Python** | ✅ | Runtime tracing (v12.3) | python-debug |
| **JavaScript** | ✅ | Runtime tracing (v1.0) | javascript-debug |
| **TypeScript** | ✅ | Static + Formal | pyprover-bridge |
| **Rust** | 🔶 | Borrow checker parsing (v0.2 in progress) | rust-debug (Phase 1) |
| **C (Safe Subset)** | 🔶 | Static + Symbolic (v0.1 in progress) | c-debug (Phase 1) |
| **C++20** | 🔶 | AST + DWARF + KLEE (v0.1 in progress) | cpp-debug (Phase 1) |
| **Go** | ✅ | Static + Formal | pyprover-bridge |
| **Java** | ✅ | Static + Formal | pyprover-bridge |
| **C#** | ✅ | Static + Formal | pyprover-bridge |
| **WebAssembly (WAT)** | ✅ | Static + Formal | pyprover-bridge |
| **NASM (x86-64)** | ✅ | Disassembly + Dataflow (v0.1 in progress) | assembly-debug (Phase 1) |
| **FASM (x86-64)** | ✅ | Disassembly + Dataflow (v0.1 in progress) | assembly-debug (Phase 1) |

**Status Key:**
- ✅ **Full support** - All debug phases available via PyProver
- 🔶 **In development** - Runtime/static layers being added in Phases 2-10

---

## Architecture

### High-Level Integration

```
┌────────────────────────────────────────────────┐
│   Master-Debugger v6 (Unified Orchestrator)   │
├────────────────────────────────────────────────┤
│                                                │
│  Phase 0: Static Analysis (per-language)      │
│  Phase 1: Runtime Debugging (Python/JS only)  │
│  Phase 2: Formal Verification (via PyProver)  │
│  Phase 3: Design Review (per-language)        │
│                                                │
├──────────────────┬──────────────────┬─────────┤
│                  │                  │         │
▼                  ▼                  ▼         ▼
Python-Debug   JS-Debug           PyProver   Other
(runtime)      (runtime)          Bridge     (phases 0/3)
│                  │                  │
│                  │    ┌─────────────┘
│                  │    │
└──────────────────┴────┴─ Normalized UnifiedReport
                          (risk_level, phases_executed,
                           timeline, variables, patterns,
                           phase_2_formal, etc.)
```

### PyProver Bridge Architecture

```
┌─────────────────────────────────────────┐
│   PyProverBridge (src/common/)          │
├─────────────────────────────────────────┤
│                                         │
│  Language Detection                     │
│  ├─ Extension-based (.py, .rs, etc.)   │
│  ├─ Heuristic-based (code content)     │
│  └─ PyProver's detector (if available) │
│                                         │
│  Verification Invocation                │
│  ├─ verify(code, language)              │
│  ├─ batch_verify(code, language)        │
│  └─ Timeout handling                    │
│                                         │
│  Output Normalization                   │
│  ├─ PyProver → UnifiedReport conversion │
│  ├─ Risk classification                 │
│  └─ Constraint → Timeline mapping       │
│                                         │
│  Error Handling                         │
│  ├─ Missing PyProver → graceful None    │
│  ├─ Timeout → empty result              │
│  └─ All exceptions caught               │
│                                         │
└─────────────────────────────────────────┘
        ▼
    PyProver v12
    (if installed)
```

---

## Usage Examples

### Example 1: Verify Python Code

```python
from debug_suite import MasterDebuggerV6

debugger = MasterDebuggerV6(use_pyprover=True)

python_code = """
def sum_array(arr):
    # @requires: len(arr) > 0
    # @ensures: result == sum(arr)
    total = 0
    for x in arr:
        total += x
    return total
"""

report = await debugger.debug_comprehensive(python_code, language="python")
print(report.risk_level)        # LOW (if verified)
print(report.pyprover_result)   # {'verified': True, 'template_type': 'ACCUMULATOR', ...}
```

### Example 2: Verify Rust Code

```python
rust_code = """
fn borrow_check() {
    let x = 5;
    let y = &x;
    println!("{}", y);
}
"""

report = await debugger.debug_comprehensive(rust_code, language="rust")
print(report.risk_level)        # LOW
print(report.pyprover_result)   # PyProver's verification result
```

### Example 3: Detect Language Automatically

```python
from debug_suite.common.pyprover_bridge import detect_language

code = "fn main() { println!('hello'); }"

language = detect_language(code)  # Returns LanguageType.RUST

report = await debugger.debug_comprehensive(code, language=str(language))
```

### Example 4: Without PyProver (Graceful Degradation)

```python
debugger = MasterDebuggerV6(use_pyprover=False)

code = "def foo(): pass"
report = await debugger.debug_comprehensive(code, language="python")

# Phase 2 (formal verification) is skipped
print(report.phases_completed)  # [STATIC, RUNTIME] (no FORMAL)
print(report.pyprover_result)   # None
```

---

## Installation

### Prerequisites

```bash
# Install debug-suite v2.0
pip install debug-suite[pyprover]

# This also installs PyProver v12+
pip install pyprover>=12.0
```

### Optional: External Tool Integration

PyProver can invoke complementary tools for each language:

```bash
# Python
pip install mypy pytest pylint

# Rust
cargo install clippy

# C/C++
sudo apt-get install clang clang-tools klee-tools

# Go
go install github.com/golangci/golangci-lint@latest

# Assembly
pip install capstone angr
```

---

## Phase 2: How PyProver Verification Works

When you call `debug_comprehensive(..., phases=["formal"])`, here's what happens:

### 1. Language Detection
```python
language = detect_language(code)  # Returns LanguageType
```

### 2. PyProver Invocation
```python
result = pyprover_bridge.verify(code, language="python")
```

### 3. Contract Extraction
PyProver parses comments/annotations:
```python
def factorial(n):
    # @requires: n >= 0
    # @ensures: result >= 1
    if n <= 1:
        return 1
    return n * factorial(n-1)
```

### 4. Template Matching
Detects: RECURSION template

### 5. Z3 Proof Generation
Proves: factorial(n) >= 1 for all n >= 0

### 6. Result Normalization
```python
UnifiedReport(
    risk_level=LOW,
    phases_executed=[0, 1, 2],
    phase_2_formal={
        'verified': True,
        'template_type': 'RECURSION',
        'constraints': [...],
    }
)
```

---

## Error Handling & Graceful Degradation

### If PyProver Not Installed

```python
# Bridge detects missing PyProver automatically
bridge = PyProverBridge(use_pyprover=True)

if not bridge.is_available():
    print("PyProver not installed, continuing without formal verification")
    # Phase 2 is skipped silently
    # Debug-suite continues with Phases 0, 1, 3
```

### If Verification Timeout

```python
# Default timeout: 30 seconds
bridge = PyProverBridge(timeout_seconds=30)

result = bridge.verify(code, language="python")
# If timeout: returns None, doesn't crash
```

### If Verification Fails

```python
# Verification error (e.g., unsatisfiable constraint)
result = {
    'verified': False,
    'error': 'Constraint unsatisfiable: x > 0 AND x < 0',
    'template_type': None,
}

# Converted to UnifiedReport with CRITICAL risk
report = bridge._convert_to_unified_report(result, "python")
assert report.risk_level == RiskLevel.CRITICAL
```

---

## Configuration

### Master-Debugger Settings

```python
from debug_suite import MasterDebuggerV6

# Enable PyProver (default: True)
debugger = MasterDebuggerV6(use_pyprover=True)

# Disable PyProver (for testing)
debugger = MasterDebuggerV6(use_pyprover=False)

# Configure timeout
debugger.pyprover_bridge.timeout_seconds = 60
```

### PyProver Bridge Settings

```python
from debug_suite.common.pyprover_bridge import PyProverBridge

bridge = PyProverBridge(
    use_pyprover=True,           # Enable/disable
    timeout_seconds=30,           # Timeout for verification
)

# Check availability
if bridge.is_available():
    print("PyProver ready")

# Get supported languages
langs = bridge.get_supported_languages()
# Returns: [LanguageType.PYTHON, LanguageType.RUST, ...]
```

---

## Troubleshooting

### "PyProver not available"

**Problem:** You see warnings about PyProver not being available.

**Solution:**
```bash
pip install pyprover>=12.0
python -c "import pyprover; print(pyprover.__version__)"
```

### "Verification timeout"

**Problem:** Verification takes too long or hangs.

**Solution:**
```python
bridge = PyProverBridge(timeout_seconds=60)  # Increase timeout
# OR
debugger = MasterDebuggerV6(use_pyprover=False)  # Skip formal verification
```

### "Constraint unsatisfiable"

**Problem:** PyProver says your contracts are contradictory.

**Example:**
```python
def foo(x):
    # @requires: x > 0
    # @requires: x < 0
    # These two can never both be true!
    return x
```

**Solution:** Review your contract annotations. They must be satisfiable.

### "Template not detected"

**Problem:** PyProver couldn't match your code to any template.

**Solution:** Your code doesn't fit the 10 universal templates. Review PyProver's template guide:
```
ACCUMULATOR, BINARY_SEARCH, RECURSION, STATE_MACHINE, MIN_MAX_LOOP,
FILTER, SCAN, SORTED_ARRAY, PARTITION, PERMUTATION
```

---

## Performance Characteristics

### Token Costs (Typical)

| Operation | Tokens | Notes |
|-----------|--------|-------|
| Language detection | 0-50 | Fast, mostly heuristics |
| verify() call | 200-800 | Depends on code size + complexity |
| batch_verify() | 500-2000 | Multiple functions |
| Full Phase 2 (all phases) | 500-1500 | Including Phases 0, 1, 3 |

### Execution Time

| Operation | Time | Notes |
|-----------|------|-------|
| detect_language() | <100ms | Heuristic-based |
| verify() | 0.1-5s | Depends on Z3 complexity |
| Total debug_comprehensive() | 1-10s | All 4 phases |

**With large code or complex constraints, times may increase.**

---

## Roadmap & Future Phases

### Phase 1: PyProver Bridge (✅ COMPLETE)
- ✅ Bridge implementation
- ✅ Language detection
- ✅ Graceful degradation
- ✅ Output normalization
- ✅ Integration tests

### Phase 2-3: Rust-Debug (In Progress)
- Borrow checker parsing (Phase 1 runtime)
- Clippy integration (Phase 0 static)
- Unsafe block analysis (Phase 3 design)

### Phase 4-6: C/C++-Debug (Scheduled)
- Clang AST parsing
- DWARF symbol reading
- KLEE symbolic execution

### Phase 7: C-Debug (Scheduled)
- Simpler C variant of C++
- strace syscall tracing

### Phase 8-10: Assembly-Debug (Research)
- Capstone disassembly
- Control flow graph building
- angr symbolic execution

---

## API Reference

### PyProverBridge Class

```python
class PyProverBridge:
    """Bridge to PyProver for formal verification."""
    
    def __init__(self, use_pyprover: bool = True, timeout_seconds: int = 30):
        """Initialize bridge."""
    
    def is_available(self) -> bool:
        """Check if PyProver is available."""
    
    def get_supported_languages(self) -> List[LanguageType]:
        """Get list of supported languages."""
    
    def verify(
        self,
        code: str,
        language: str,
        function_name: Optional[str] = None,
    ) -> Optional[UnifiedReport]:
        """Verify code with PyProver."""
    
    def batch_verify(
        self,
        code: str,
        language: str,
    ) -> Optional[Dict[str, UnifiedReport]]:
        """Verify all functions in code."""
    
    def detect_language(
        self,
        code: str,
        filename: Optional[str] = None,
    ) -> Optional[LanguageType]:
        """Detect code language."""
```

### Module-Level Functions

```python
def invoke_pyprover(
    code: str,
    language: str,
    function_name: Optional[str] = None,
) -> Optional[UnifiedReport]:
    """Convenience function: invoke PyProver."""

def detect_language(
    code: str,
    filename: Optional[str] = None,
) -> Optional[LanguageType]:
    """Convenience function: detect language."""
```

---

## Related Documentation

- **PyProver Guide:** https://github.com/anthropics/pyprover (external)
- **Debug-Suite v2.0 SKILL.md:** Overview of all components
- **Phased Implementation Plan:** `DEBUG-SUITE-PHASED-BREAKDOWN.md`
- **Multi-Language Strategy:** `debug-suite-multilanguage-strategy-REVISED.md`

---

## Support

For issues with PyProver integration:
1. Check that PyProver is installed: `pip list | grep pyprover`
2. Enable debug logging: Set `DEBUG_SUITE_VERBOSE=1`
3. Review error messages in stderr (not printed by default)
4. Try disabling PyProver: `MasterDebuggerV6(use_pyprover=False)`

---

**Last Updated:** June 28, 2026  
**Debug-Suite Version:** 2.0.0  
**PyProver Integration Status:** Production Ready
