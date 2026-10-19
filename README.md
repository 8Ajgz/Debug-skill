# Debug Suite v2.9.6

> **Provenance:** all code in this repository was written by an unspecified version of Claude, unless a commit or file says otherwise.
>
> All commits from this account were made by Claude under the oversight of Maxwell Morrongiello unless otherwise specified.

Production-ready unified debugging and verification suite combining 8 complementary tools for Python and JavaScript: python-debug, javascript-debug, pyprover, test-generator, code-orchestrator, troubleshooting, master-debugger-v5, and common utilities with unified interoperability layer.

## Quick Start

```python
from debug_suite import MasterDebuggerV5, LanguageDetector

debugger = MasterDebuggerV5()

# Automatically detects Python or JavaScript
py_code = "def divide(a, b):\n    return a / b"
js_code = "let x = null; console.log(x.foo);"

py_report = debugger.debug(py_code)
js_report = debugger.debug(js_code)

print(py_report.summary)  # Risk level, phases executed, issues found
print(js_report.summary)
```

## Features

**4-Phase Automated Debugging** | **Python & JavaScript Support** | **Formal Verification** | **Comprehensive Testing** | **Codebase Analysis** | **Problem Diagnosis** | **Unified Interoperability**

For detailed feature descriptions, see **SKILL.md**.

## Installation

```bash
pip install debug-suite
```

Or from local file:
```bash
pip install /path/to/debug-suite-1.2.skill
```

## Documentation

- **[SKILL.md](SKILL.md)** – Complete API reference, use cases, workflows, token costs
- **[API.md](API.md)** – Auto-generated operation signatures and schemas
- **[INTEROP.yaml](INTEROP.yaml)** – Interoperability metadata and operation contracts
- **[CHANGELOG.md](CHANGELOG.md)** – Version history and breaking changes
- **[src/common/interop.py](src/common/interop.py)** – Unified interop layer documentation

## License

MIT
