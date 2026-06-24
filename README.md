# Verification-Debugging-Suite v1.0

Production-ready unified verification and debugging suite combining 7 complementary tools.

## Features

- **4-Phase Automated Debugging** (Master-Debugger-v5)
  - Phase 0: Static analysis (mypy, pylint, bandit)
  - Phase 1: Runtime tracing (python-debug)
  - Phase 2: Formal verification (pyprover + Z3)
  - Phase 3: Design review (troubleshooting)

- **Formal Contract Verification** (PyProver v14.0)
  - Z3 SMT solver integration
  - Loop invariant verification
  - Property-based testing

- **Comprehensive Test Generation** (test-generator v1.1)
  - Edge cases and boundary values
  - Mutation testing
  - Metamorphic tests
  - Red-team adversarial tests

- **Large-Scale Analysis** (code-orchestrator v1.1)
  - Multi-function codebase verification
  - GitHub project analysis
  - Progress checkpointing

- **Universal Troubleshooting** (troubleshooting v1.0)
  - 5-phase diagnosis methodology
  - Problem classification
  - Root cause analysis
  - Solution recommendation

## Installation

```bash
pip install verification-debugging-suite
```

## Quick Start

```python
from verification_debugging_suite import MasterDebuggerV5

debugger = MasterDebuggerV5()
code = """
def divide(a, b):
    return a / b
"""

report = debugger.debug(code)
print(report.summary)
```

## Components

- `python-debug` - Runtime execution tracing (v12.3)
- `pyprover` - Formal verification with Z3 (v14.0)
- `test-generator` - Test generation and mutation (v1.1)
- `code-orchestrator` - Codebase analysis (v1.1)
- `troubleshooting` - 5-phase diagnosis (v1.0)
- `master-debugger-v5` - 4-phase orchestrator (v5.0)

## Documentation

See `SKILL.md` for complete API reference and examples.

## License

MIT
