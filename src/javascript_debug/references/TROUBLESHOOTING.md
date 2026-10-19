# Troubleshooting Guide

## Common Issues & Solutions

### Issue 1: Code Not Being Traced

**Symptom:** Variables show 0 mutations in timeline

**Cause:** Code instrumentation limitations with Function constructor

**Solution:** Use the DebugReport API directly

```javascript
// ✗ Won't track variables
const report = executeWithDebug('let x = 10; let y = 20;');
console.log(report.variables.size);  // 0

// ✓ Works perfectly
const report = new DebugReport('test');
report.logVariable(1, 'x', 10);
report.logVariable(2, 'y', 20);
console.log(report.dumpVariables());  // {x, y}
```

**Workaround:** All diagnostic tests, examples, and production use cases prefer the API approach.

---

### Issue 2: "TypeError: Cannot find module"

**Symptom:** Error when requiring debug-engine.js

**Cause:** File not in expected path

**Solution:** Verify file location and require correctly

```javascript
// Verify files exist
ls scripts/debug-engine.js
ls scripts/bug-patterns.js

// Require from correct path
const { executeWithDebug } = require('./scripts/debug-engine.js');
const { BugPatternDetector } = require('./scripts/bug-patterns.js');

// Or from scripts directory
const { executeWithDebug } = require('./debug-engine.js');
```

---

### Issue 3: Code Execution Timeout

**Symptom:** "Execution timeout after Xms" error

**Cause:** Code has infinite loop or runs too long

**Solution:** Increase timeout or fix the code

```javascript
// ✗ Times out
executeWithDebug('while (true) {}', {}, { timeout: 1000 });

// ✓ Increase timeout
executeWithDebug('while (true) {}', {}, { timeout: 5000 });

// ✓ Fix the code
executeWithDebug('for (let i = 0; i < 5; i++) { }', {}, { timeout: 1000 });
```

---

### Issue 4: No Patterns Detected (But Should Be)

**Symptom:** Code has bug, detector finds 0 patterns

**Cause:** Pattern requires specific conditions to trigger

**Solution:** Check if pattern detection applies

```javascript
// ✗ Type mismatch may not be detected without mutation
const code = 'let x = "5"; let y = x + 3;';

// ✓ Add mutation to make it detectable
const code = `
  let x = "5";
  let y = x;
  y = 5;  // Now type changes and gets detected
`;
```

**Note:** Some patterns (FLOATING_POINT, MEMORY_LEAK) have low confidence and only trigger in specific scenarios.

---

### Issue 5: Aliasing Not Detected

**Symptom:** Variables share same object but aliases.size is 0

**Cause:** Different ref IDs or single ref

**Solution:** Verify variables actually alias

```javascript
// ✗ Different objects
const report = new DebugReport();
report.logVariable(1, 'a', {}, 'ref_1');
report.logVariable(2, 'b', {}, 'ref_2');  // Different ref
const aliases = report.getTrueAliases();  // Empty

// ✓ Same object
const report = new DebugReport();
const obj = {};
report.logVariable(1, 'a', obj, 'ref_1');
report.logVariable(2, 'b', obj, 'ref_1');  // Same ref
const aliases = report.getTrueAliases();  // Found!
```

---

### Issue 6: Exception Not Captured

**Symptom:** Code throws but exceptionInfo is null

**Cause:** Exception in different scope or not in code string

**Solution:** Ensure error occurs in executed code

```javascript
// ✗ External try/catch - exception not in executeWithDebug
const code = 'throw new Error("test");';
try {
  const report = executeWithDebug(code);  // Catches internally
} catch (e) {
  // Not here
}

// ✓ Check report.exceptionInfo
const report = executeWithDebug('throw new Error("test");');
if (report.exceptionInfo) {
  console.log(report.exceptionInfo);  // Found!
}
```

---

### Issue 7: Promise Events Missing

**Symptom:** getPromiseEvents() returns empty array

**Cause:** Promise created outside executeWithDebug scope

**Solution:** Create Promise within code string

```javascript
// ✗ Promise created outside
const p = new Promise(resolve => resolve(42));
const report = executeWithDebug('console.log("test")');  // No Promises

// ✓ Create Promise in code
const code = `
  let p = new Promise(resolve => resolve(42));
  p.then(v => console.log(v));
`;
const report = executeWithDebug(code);
console.log(report.getPromiseEvents());  // Found!
```

---

### Issue 8: Out of Memory

**Symptom:** "JavaScript heap out of memory" or very slow

**Cause:** Large code execution with many events

**Solution:** Reduce maxTimelineSize or optimize code

```javascript
// ✗ Large code with many events
const largeCode = 'for (let i = 0; i < 1000000; i++) {}';
const report = executeWithDebug(largeCode);  // Memory intensive

// ✓ Limit timeline
const report = executeWithDebug(largeCode, {}, {
  maxTimelineSize: 100  // Only keep last 100 events
});

// ✓ Disable variable tracing
const report = executeWithDebug(largeCode, {}, {
  traceVariables: false  // No mutation tracking
});
```

---

### Issue 9: Incorrect Results

**Symptom:** Pattern confidence is lower than expected

**Cause:** Detector uses heuristics, not static analysis

**Solution:** Understand confidence levels

```javascript
// Confidence depends on evidence
const report = new DebugReport();
report.captureException(new TypeError('Cannot read property'));
const patterns = new BugPatternDetector(report).analyze();

// High confidence (95%): Clear TypeError message
// Medium confidence (70%): Type changed without explicit cause
// Low confidence (40%): Could be many things
```

**Note:** Run code execution to gather evidence. More context = higher confidence.

---

## Performance Issues

### Slow Execution

**Check:**
1. Is `traceVariables: true`? (default) - Try setting to `false`
2. Is code very large? - Set `maxTimelineSize: 100`
3. Is timeout high? - Reduce timeout
4. Are patterns running? - Use `report.analyze()` sparingly

```javascript
// Fast mode
const report = executeWithDebug(code, {}, {
  traceVariables: false,
  maxTimelineSize: 100,
  timeout: 1000
});
```

---

## Debugging the Debugger

### Enable Detailed Logging

```javascript
const report = new DebugReport('debug');
report.logVariable(1, 'x', 10);
report.logVariable(2, 'x', 20);

console.log('Variables:', report.variables);
console.log('Timeline:', report.timeline);
console.log('JSON:', JSON.stringify(report.toJSON(), null, 2));
```

### Check Internal State

```javascript
const report = new DebugReport();
// ... populate with data ...

// Debug info
console.log('Timeline length:', report.timeline.length);
console.log('Variable count:', report.variables.size);
console.log('Promises:', report.promises.length);
console.log('Exception:', report.exceptionInfo?.type);

// Verify data integrity
const aliases = report.getTrueAliases();
aliases.forEach((vars, ref) => {
  console.log(`Ref ${ref}: ${vars.join(', ')}`);
});
```

---

## Getting Help

1. **Check examples.js** - See working code
2. **Read API.md** - Complete API reference
3. **Review PATTERNS.md** - Pattern explanation
4. **Run tests.js** - Verify installation
5. **Check this guide** - Troubleshooting tips

---

## Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| Code instrumentation | Variables not tracked in executeWithDebug | Use DebugReport API |
| Heuristic patterns | Some patterns lower confidence | Run with more evidence |
| Single-threaded | Can't debug workers | Use reportable state |
| Code scope | External Promises not tracked | Create Promise in code |

