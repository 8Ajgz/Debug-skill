# PyProver v11.2 - Language Adapter Development Guide (RECOVERED FRAGMENT)

**Source:** https://claude.ai/chat/d0b4e00c-15af-4cf8-bdf7-219dee000dc2 ("Rust language adapter for skill creator"), https://claude.ai/chat/c9d14d64-a052-48ff-9b3e-b6b8826a0736 ("Checking file errors with pyprover"), https://claude.ai/chat/eb50e995-48c6-44d3-9e6b-b3ac35a005f8 ("WebAssembly language adapter for skill creator")

**NOT TESTED/VERIFIED IN THIS SESSION.** This recovers the architecture/intro
of a guide that doesn't exist anywhere in the current `src/pyprover/` - the
bundled `ContractVerifier` has no adapter system at all (see roadmap.md
§2.2). Full guide was reportedly ~13 sections / "12,000 lines of
documentation" across all adapters combined per the v11.2 completion
summary; only the interface description and template list below were
captured by the search queries used this session.

---

**For Claude: Creating New Language Adapters in 15 Minutes**

This guide enables Claude to add new programming languages to PyProver
quickly using a structured template system.

## Part I: Anatomy of a Language Adapter

Every language adapter consists of three components:

### 1. Contract Syntax Definition

How to express @requires, @ensures, @assume in the language:

| Language | Syntax |
|---|---|
| Python | Decorators: `@requires(...)`, `@ensures(...)` |
| JavaScript / TypeScript | JSDoc comments: `/** @requires ... */` |
| C++ | Attributes: `[[pre: ...]]`, `[[post: ...]]` |
| Go | Comments: `// @requires ...` |
| WebAssembly (WAT) | Block comments: `(;; @requires ... ;;)` |
| NASM / FASM | Semicolon comments: `; @requires ...` |

### 2. Template Examples

All 10 verification templates must have working code examples in the new
language:

- `ACCUMULATOR`
- `MIN_MAX_LOOP`
- `FILTER`
- `BINARY_SEARCH`
- `RECURSION`
- `STATE_MACHINE`
- `SCAN`
- `SORTED_ARRAY`
- `PARTITION`
- `PERMUTATION`

### 3. The `LanguageAdapter` interface

(Interface name/method list reconstructed from the WebAssembly-adapter
session's summary, which states: *"The skill uses a LanguageAdapter
interface pattern where each language implements six core methods."*)

```python
class LanguageAdapter:
    """
    Every per-language adapter (PythonAdapter, JavaScriptAdapter,
    RustAdapter, CppAdapter, GoAdapter, JavaAdapter, CSharpAdapter,
    WasmAdapter, NasmAdapter, FasmAdapter, ...) implements:
    """

    def language_name(self) -> str:
        """Return the canonical language identifier, e.g. 'python', 'rust'."""
        ...

    def parse_function(self, source_code: str, func_name: str) -> dict:
        """
        Parse source_code and return an AST-like representation of the
        named function. See pyprover_js_nodejs_parser_fix.py in this folder
        for a worked example (JS, via Node.js subprocess + acorn).
        """
        ...

    def extract_contracts(self, ast_data: dict) -> dict:
        """
        Extract @requires/@ensures/@assume clauses from the parsed function,
        using this language's contract syntax (see table above). See
        pyprover_multiline_contract_regex_fix.py in this folder for a
        worked example of one specific extraction bug (Python, multiline).
        """
        ...

    def extract_variables(self, ast_data: dict) -> dict:
        """Extract parameter names/types and local variable declarations."""
        ...

    def extract_loops(self, ast_data: dict) -> list:
        """
        Extract loop structures (for/while) for loop-invariant verification.
        See pyprover_v13_loop_verifier.py in this folder for the verifier
        these feed into.
        """
        ...

    def infer_template(self, ast_data: dict) -> str:
        """
        Classify the function as one of the 10 verification templates
        listed above (ACCUMULATOR, BINARY_SEARCH, etc.) so the verifier
        knows which proof strategy/invariant-generation approach to use.
        """
        ...
```

## Notes for restoration

- This entire system is independent of and predates the bundled
  `common.interop.LanguageType` enum used throughout the current suite -
  porting this means building a translation layer, not just dropping these
  files in.
- The 12-language claim in the current `SKILL.md` ("12-language support via
  PyProver bridge") refers to this system, but as documented in roadmap.md
  §1/§2.2, none of these adapters exist in the bundled code - the claim is
  aspirational/inherited from this older branch's documentation, not a
  description of what `src/pyprover/contract_verifier.py` actually does
  today.
- Before rebuilding this, re-read `verification_stack_and_bugs.md` (this
  folder) - the same source chats found 5 concrete bugs in this exact
  adapter system the last time it was tested against real code (Chromium
  patterns). Don't reintroduce them.
