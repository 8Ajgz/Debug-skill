"""
RECOVERED FRAGMENT - NOT TESTED IN THIS SESSION
Source: https://claude.ai/chat/f1b0a59a-8372-4030-a2e3-89e18b07fc26
("Testing pyprover on chromium codebase")

Bug #2 from the Chromium red-team testing session: the JavaScript adapter's
Python `esprima` parser took ~39ms per function vs. 3-4ms for an equivalent
Node.js `acorn` subprocess call - a 10x slowdown purely from using a Python
AST library instead of shelling out to the JS ecosystem's native tooling.

This fragment shows both the "before" (esprima, slow) and the recommended
"after" (Node.js subprocess, fast) - two versions of the fix were drafted
across the session, captured here as both `_parse_with_esprima` (kept as a
fallback when Node.js isn't installed) and `_parse_with_nodejs` (the fast
path). Confirmed by this suite's own environment-capability research
(roadmap.md §7) that `node`/npm-installable `acorn` should be available in
this sandbox - this fix was never blocked on tooling availability, only on
nobody porting it into the bundled `pyprover_bridge.py`.

GAP: this was written against a standalone `PyProverCore`-style adapter
class, not the current bundled `src/pyprover/contract_verifier.py` (which
doesn't do real per-language parsing at all - see roadmap.md §2.2). Wiring
this in means first giving ContractVerifier real per-language adapters,
which this fragment alone doesn't provide for languages other than JS.
"""

import subprocess
import json
import tempfile
from pathlib import Path
from typing import Dict, Any


class JavaScriptParserMixin:
    """Mixin showing both the slow and fast JS parsing paths."""

    def parse_function(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """Parse JavaScript function using Node.js for 10x speed improvement."""

        # Check if Node.js is available
        try:
            subprocess.run(['node', '--version'], capture_output=True, timeout=1, check=True)
            use_nodejs = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            # Fallback to Python esprima
            use_nodejs = False

        if use_nodejs:
            return self._parse_with_nodejs(source_code, func_name)
        else:
            return self._parse_with_esprima(source_code, func_name)

    def _parse_with_esprima(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """SLOW PATH (~39ms/function). Kept as fallback when Node.js is unavailable."""
        from esprima import parse as esprima_parse

        ast = esprima_parse(source_code)

        for node in ast['body']:
            if node['type'] == 'FunctionDeclaration' and node['id']['name'] == func_name:
                return {
                    'ast': node,
                    'source': source_code,
                    'language': 'javascript',
                }

        raise ValueError(f"Function '{func_name}' not found")

    def _parse_with_nodejs(self, source_code: str, func_name: str) -> Dict[str, Any]:
        """FAST PATH (~3-4ms/function) - requires `npm install acorn` available to node."""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(source_code)
            temp_file = f.name

        try:
            # Node.js script to extract function AST. NOTE: f-string injection
            # of temp_file/func_name into a JS source string is unsafe input
            # handling if either value can be attacker-controlled - this was
            # a recommended/draft fix, not a security-reviewed one. Sanitize
            # or pass via env vars / a JSON sidecar file instead of string
            # interpolation before using this against untrusted code.
            extract_script = f'''
const parser = require('acorn');
const fs = require('fs');

const code = fs.readFileSync('{temp_file}', 'utf-8');

try {{
    const ast = parser.parse(code, {{
        ecmaVersion: 2022,
        sourceType: 'module'
    }});

    // Find function by name
    const func = ast.body.find(n =>
        (n.type === 'FunctionDeclaration' && n.id && n.id.name === '{func_name}') ||
        (n.type === 'VariableDeclaration' && n.declarations.some(d =>
            d.init && d.init.type === 'FunctionExpression' && d.id && d.id.name === '{func_name}'
        ))
    );

    if (func) {{
        // GAP: the recovered snippet is cut off here - the JSON.stringify
        // payload shape (what fields of `func` get sent back) was not
        // captured. Reconstruct based on what `_parse_with_esprima` above
        // returns ('ast', 'source', 'language' keys) for consistency.
        console.log(JSON.stringify({{
            type: func.type,
            name: func.id ? func.id.name : null,
            // ... remaining fields not recovered
        }}));
    }} else {{
        process.exit(1);
    }}
}} catch (e) {{
    console.error(e.message);
    process.exit(1);
}}
'''
            result = subprocess.run(
                ['node', '-e', extract_script],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return {
                    'ast': json.loads(result.stdout),
                    'source': source_code,
                    'language': 'javascript',
                }
            else:
                raise ValueError(f"Function '{func_name}' not found or parse error: {result.stderr}")
        finally:
            Path(temp_file).unlink(missing_ok=True)
