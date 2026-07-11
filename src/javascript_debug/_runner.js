/**
 * _runner.js: subprocess entrypoint used by ../javascript_debug/__init__.py's
 * JavaScriptDebugger.execute_with_debug(). Not part of the public JS API
 * (debug-engine.js / bug-patterns.js are); this just wires the two
 * together and serializes the result to JSON on stdout so the Python
 * side (which has no way to hold a live JS Map/class-instance across a
 * subprocess boundary) gets a single JSON-safe result.
 *
 * Pattern detection must happen in this same process, not as a separate
 * later step: BugPatternDetector reads this.report.variables as a live
 * Map and calls this.report.getTrueAliases()/getVariableMutations(),
 * none of which survive a report.toJSON() round-trip. So execution and
 * pattern analysis are fused here into one pass, and only the combined,
 * already-analyzed result crosses the process boundary.
 *
 * Usage: node _runner.js <code-file> [global-scope-json] [options-json]
 * Output (stdout): {"success": true, "report": {...}, "patterns": [...]}
 *               or {"success": false, "error": "..."}
 */

const fs = require('fs');
const path = require('path');
const { executeWithDebug } = require(path.join(__dirname, 'debug-engine.js'));
const { BugPatternDetector } = require(path.join(__dirname, 'bug-patterns.js'));

function main() {
  const codeFile = process.argv[2];
  const scopeArg = process.argv[3];
  const optionsArg = process.argv[4];

  if (!codeFile) {
    process.stdout.write(JSON.stringify({ success: false, error: 'no code file provided' }));
    return;
  }

  let code, globalScope, options;
  try {
    code = fs.readFileSync(codeFile, 'utf8');
    globalScope = scopeArg ? JSON.parse(scopeArg) : {};
    options = optionsArg ? JSON.parse(optionsArg) : {};
  } catch (e) {
    process.stdout.write(JSON.stringify({ success: false, error: `setup error: ${e.message}` }));
    return;
  }

  try {
    // The code under debug may call console.log/warn/error itself, and
    // debug-engine.js's executeWithDebug() always forwards those calls to
    // the real process stdout regardless of what's passed via
    // globalScope (its fullScope construction spreads globalScope first,
    // then unconditionally overwrites `console` -- so a custom console
    // shim passed in here would silently never be used). That direct
    // pass-through interleaves with this script's own final
    // JSON.stringify output on the same stdout stream and corrupts it
    // (confirmed by direct testing: a script as simple as `let x = 1+2;
    // console.log(x)` broke JSON parsing on the Python side). Since
    // stdout here is a machine-readable result channel, not a display,
    // it's suppressed during execution. This does mean the debugged
    // code's own console output is currently dropped rather than
    // captured and returned -- a real, documented limitation, not a
    // silent one; capturing it properly would require changing
    // debug-engine.js's fullScope spread order to let a caller-provided
    // console take precedence, which is out of scope for this fix.
    const realStdoutWrite = process.stdout.write.bind(process.stdout);
    let report;
    try {
      process.stdout.write = () => true;
      report = executeWithDebug(code, globalScope, options);
    } finally {
      process.stdout.write = realStdoutWrite;
    }

    let patterns = [];
    try {
      patterns = new BugPatternDetector(report).analyze();
    } catch (e) {
      // Pattern detection failing shouldn't discard a successful
      // execution report -- surface it as an empty pattern list plus
      // an explicit note, not a whole-call failure.
      process.stdout.write(JSON.stringify({
        success: true,
        report: report.toJSON(),
        patterns: [],
        pattern_analysis_error: e.message,
      }));
      return;
    }
    process.stdout.write(JSON.stringify({
      success: true,
      report: report.toJSON(),
      patterns: patterns,
    }));
  } catch (e) {
    process.stdout.write(JSON.stringify({ success: false, error: e.message }));
  }
}

main();
