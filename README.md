# Verification-Debugging-Suite v1.1

Production-ready unified verification and debugging suite combining 7 complementary tools: python-debug, pyprover, test-generator, code-orchestrator, troubleshooting, master-debugger-v5, and common utilities.

## Quick Start

```python
from verification_debugging_suite import MasterDebuggerV5

debugger = MasterDebuggerV5()
code = "def divide(a, b):\n    return a / b"

report = debugger.debug(code)
print(report.summary)  # Risk level, phases executed, issues found
```

## Features

**4-Phase Automated Debugging** | **Formal Verification** | **Comprehensive Testing** | **Codebase Analysis** | **Problem Diagnosis**

For detailed feature descriptions, see **SKILL.md**.

## Installation

```bash
pip install verification-debugging-suite
```

Or from local file:
```bash
pip install /path/to/verification-debugging-suite-1.1.skill
```

## Documentation

- **[SKILL.md](SKILL.md)** – Complete API reference, use cases, workflows, token costs
- **[API.md](API.md)** – Auto-generated operation signatures and schemas
- **[INTEROP.yaml](INTEROP.yaml)** – Interoperability metadata and operation contracts
- **[CHANGELOG.md](CHANGELOG.md)** – Version history and breaking changes

## License

MIT
