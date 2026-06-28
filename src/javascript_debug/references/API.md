# JavaScript-Debug v1.0 - Complete API Reference

## Table of Contents
1. [DebugReport Class](#debugreport-class)
2. [executeWithDebug Function](#executewithdebugging-function)
3. [BugPatternDetector Class](#bugpatterndetector-class)
4. [Data Structures](#data-structures)
5. [Error Handling](#error-handling)

---

## DebugReport Class

Core data structure that holds execution trace information.

### Constructor

```javascript
const report = new DebugReport(description = "execution trace");
```

### Methods

#### logVariable(lineIndex, varName, value, metadata = {})
Record a variable assignment or mutation.

```javascript
report.logVariable(1, 'x', 42);
report.logVariable(2, 'x', 43);
```

#### getVariableMutations(varName)
Get complete mutation history for a variable.

**Returns:** `Array<{lineIndex, value, timestamp, index}>`

```javascript
const muts = report.getVariableMutations('myVar');
// [
//   { lineIndex: 1, value: 0, timestamp: 0, index: 0 },
//   { lineIndex: 5, value: 1, timestamp: 4, index: 1 }
// ]
```

#### getTrueAliases()
Identify variables sharing the same object reference.

**Returns:** `Map<refId, Array<varName>>`

```javascript
const aliases = report.getTrueAliases();
// Map {
//   'ref_abc123' => ['original', 'copy', 'ref']
// }
```

#### getCallStackAt(lineIndex)
Get function call stack at a specific execution point.

**Returns:** `Array<string>` - Function names in call stack

```javascript
const stack = report.getCallStackAt(42);
// ['main', 'processData', 'analyze']
```

#### captureException(error, lineIndex, locals)
Record an exception with context.

```javascript
try {
  throw new RangeError("Value out of range");
} catch (e) {
  report.captureException(e, 42, { x: 10, y: 20 });
}
```

#### logPromiseCreated(lineIndex, promiseId, executor)
Record Promise creation.

#### logPromiseResolved(lineIndex, promiseId, value)
Record Promise resolution.

#### logPromiseRejected(lineIndex, promiseId, reason)
Record Promise rejection.

#### getPromiseEvents()
Get all Promise-related events.

**Returns:** `Array<{type, promiseId, value|reason, ...}>`

```javascript
const events = report.getPromiseEvents();
// Events with type: 'promise_created', 'promise_resolved', 'promise_rejected'
```

#### logAsyncPoint(lineIndex, functionName, state = 'created')
Record async/await operations.

#### getAsyncEvents()
Get all async/await events.

**Returns:** `Array<{functionName, state, timestamp}>`

#### getTimeline()
Get raw event timeline.

**Returns:** `Array<{type, lineIndex, timestamp, ...}>`

#### generateHumanReadable()
Generate formatted, readable execution trace.

**Returns:** `string` - Multi-line formatted report

```javascript
console.log(report.generateHumanReadable());
// ======================================================================
// DEBUG REPORT: test execution
// ======================================================================
// Duration: 5ms
// Events: 42
// ...
```

#### dumpVariables()
Export all variables with mutation history.

**Returns:** `Object` with structure:
```javascript
{
  varName: {
    current: value,
    mutations: count,
    history: [{line, value}, ...]
  }
}
```

#### toJSON()
Export complete report as JSON.

**Returns:** `{description, duration, timeline, variables, promises, asyncEvents, exceptionInfo}`

---

## executeWithDebug Function

Execute JavaScript code with full debugging.

```javascript
const report = executeWithDebug(code, globalScope, options);
```

### Parameters

**code** (string, required)
JavaScript code to execute.

```javascript
const code = `
  let x = 10;
  let y = x + 5;
`;
```

**globalScope** (object, optional)
Variables and functions available in executed code.

```javascript
const globals = {
  config: { timeout: 5000 },
  helper: (x) => x * 2
};
const report = executeWithDebug(code, globals);
```

**options** (object, optional)
- `traceVariables` (boolean, default: true) - Track variable changes
- `maxTimelineSize` (number, default: 1000) - Max events to store
- `timeout` (number, default: 5000) - Timeout in milliseconds

```javascript
const report = executeWithDebug(code, {}, {
  timeout: 2000,
  traceVariables: true
});
```

### Return Value

`DebugReport` instance with complete execution trace.

### Example

```javascript
const { executeWithDebug } = require('./debug-engine.js');

const code = `
  let arr = [1, 2, 3];
  let copy = arr;
  copy.push(4);
`;

const report = executeWithDebug(code);
console.log(report.generateHumanReadable());
console.log(report.getTrueAliases());
```

---

## BugPatternDetector Class

Automatic bug pattern detection.

### Constructor

```javascript
const detector = new BugPatternDetector(debugReport);
```

### Methods

#### analyze()
Run all pattern detectors.

**Returns:** `Array<DetectedPattern>`

```javascript
const patterns = detector.analyze();
// Array of detected issues
```

#### generateCombinedReport()
Generate summary of all patterns grouped by severity.

**Returns:** `string` - Formatted report

```javascript
console.log(detector.generateCombinedReport());
// ======================================================================
// BUG PATTERN ANALYSIS REPORT
// ======================================================================
// Patterns Found: 3
// 
// CRITICAL (1):
//   - unhandled_promise_rejection: Promise rejected without catch
// 
// HIGH (2):
//   - null_reference: Cannot read property
//   - aliasing_mutation: Shared reference mutation
// ...
```

---

## Data Structures

### DetectedPattern

Represents a detected bug pattern.

```javascript
{
  patternType: string,    // 'null_reference', 'type_mismatch', etc.
  severity: string,       // 'critical' | 'high' | 'medium' | 'low'
  confidence: number,     // 0.0 to 1.0
  description: string,    // What the bug is
  location: number,       // Line where bug occurs
  rootCause: string,      // Why it happened
  suggestion: string,     // How to fix it
  fixExample: string      // Code example
}
```

### Methods on DetectedPattern

#### generateReport()
Generate detailed formatted report for this pattern.

**Returns:** `string`

```javascript
const pattern = patterns[0];
console.log(pattern.generateReport());
// ======================================================================
// BUG PATTERN DETECTED: NULL_REFERENCE
// ======================================================================
// Severity: HIGH
// Confidence: 95%
// Location: Line 5
// Description: Attempted to access property of null or undefined
// ...
```

---

## Error Handling

### Exception Info

When code throws an exception:

```javascript
const report = executeWithDebug('let x = null; x.prop;');

if (report.exceptionInfo) {
  console.log(report.exceptionInfo.type);      // 'TypeError'
  console.log(report.exceptionInfo.message);   // Error message
  console.log(report.exceptionFrame);          // Variables at error
  console.log(report.exceptionLine);           // Line number
}
```

### Timeout Handling

Infinite loops are caught automatically:

```javascript
const report = executeWithDebug(
  'while (true) {}',
  {},
  { timeout: 100 }  // 100ms timeout
);

if (report.exceptionInfo) {
  if (report.exceptionInfo.message.includes('timeout')) {
    console.log('Code timed out - infinite loop detected');
  }
}
```

---

## Pattern Types Reference

| Type | Severity | Confidence | When Detected |
|------|----------|-----------|---------------|
| NULL_REFERENCE | High | 95% | TypeError: Cannot read property |
| TYPE_MISMATCH | Medium | 70% | Type changed during execution |
| OFF_BY_ONE | High | 80% | Array index out of bounds |
| ALIASING_MUTATION | High | 95% | Multiple vars share same ref |
| UNHANDLED_PROMISE | Critical | 90% | Promise rejected without handler |
| RACE_CONDITION | Medium | 60% | Async operation timing issue |
| CLOSURE_CAPTURE | Low | 50% | Variable capture in closure |
| PROTOTYPE_POLLUTION | Medium | 70% | Prototype chain modified |
| MEMORY_LEAK | Low | 40% | Potential circular reference |
| FLOATING_POINT | Low | 60% | Precision artifacts detected |

---

## Quick Reference

```javascript
// Execute code with debugging
const report = executeWithDebug(code, globals, options);

// Analyze results
const vars = report.dumpVariables();
const muts = report.getVariableMutations('x');
const aliases = report.getTrueAliases();
const promises = report.getPromiseEvents();

// Detect patterns
const detector = new BugPatternDetector(report);
const patterns = detector.analyze();

// Generate reports
console.log(report.generateHumanReadable());
console.log(detector.generateCombinedReport());

// Check for errors
if (report.exceptionInfo) {
  console.log(report.exceptionInfo);
}
```
