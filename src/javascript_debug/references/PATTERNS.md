# Bug Pattern Detection Guide

## 10 Patterns Explained

### 1. NULL_REFERENCE

**What:** Accessing property of null or undefined

**Example:**
```javascript
let obj = null;
let value = obj.property;  // TypeError!
```

**How to detect:**
```javascript
const code = 'let x = null; x.prop;';
const report = executeWithDebug(code);
const detector = new BugPatternDetector(report);
const patterns = detector.analyze();
// Detects: null_reference
```

**How to fix:**
```javascript
// Before
let value = obj.property;

// After
let value = obj?.property ?? defaultValue;

// Or guard
if (obj !== null) {
  let value = obj.property;
}
```

---

### 2. TYPE_MISMATCH

**What:** Type coercion surprises and unexpected type changes

**Example:**
```javascript
let x = "5";
let y = x + 3;  // "53" not 8!

let z = x;
z = 5;          // Type changed string → number
```

**Confidence:** 70% (requires mutation tracking)

**How to fix:**
```javascript
// Before
let y = x + 3;  // Assumes x is number

// After
let y = Number(x) + 3;  // Explicit conversion
let y = parseInt(x, 10) + 3;  // For integers
```

---

### 3. OFF_BY_ONE

**What:** Loop boundary errors

**Example:**
```javascript
let arr = [1, 2, 3];
for (let i = 0; i <= arr.length; i++) {
  console.log(arr[i]);  // Last iteration: undefined
}
```

**How to fix:**
```javascript
// Wrong
for (let i = 0; i <= arr.length; i++)

// Right
for (let i = 0; i < arr.length; i++)
```

---

### 4. ALIASING_MUTATION

**What:** Multiple variables reference same object, mutations affect all

**Example:**
```javascript
let original = [1, 2, 3];
let copy = original;
copy.push(4);
// original is now [1, 2, 3, 4]!
```

**Detection:** 95% confidence (exact match)

**How to fix:**
```javascript
// Before
let copy = original;

// After - Shallow copy
let copy = [...original];
let copy = original.slice();

// After - Deep copy (objects)
let copy = JSON.parse(JSON.stringify(original));
let copy = structuredClone(original);  // Modern
```

---

### 5. UNHANDLED_PROMISE

**What:** Promise rejection without .catch() or try/catch

**Example:**
```javascript
let p = new Promise((resolve, reject) => {
  reject(new Error("Something failed"));
});
// No .catch() - unhandled rejection!
```

**Severity:** CRITICAL

**How to fix:**
```javascript
// Before
let p = somePromise();

// After - With catch
somePromise().catch(err => {
  console.error("Handled:", err);
});

// After - With async/await
async function main() {
  try {
    await somePromise();
  } catch (err) {
    console.error("Handled:", err);
  }
}
```

---

### 6. RACE_CONDITION

**What:** Async operations with timing dependencies

**Example:**
```javascript
let data = null;
fetch('/api/data').then(d => {
  data = d;
});
console.log(data);  // null - fetch not done yet!
```

**How to fix:**
```javascript
// Before
fetch('/api/data').then(d => { data = d; });
console.log(data);  // Race!

// After
const data = await fetch('/api/data');
console.log(data);  // Safe

// Or
fetch('/api/data').then(d => {
  console.log(d);  // Safe here
});
```

---

### 7. CLOSURE_CAPTURE

**What:** Variables captured by closure behave unexpectedly

**Example:**
```javascript
let funcs = [];
for (var i = 0; i < 3; i++) {
  funcs.push(() => console.log(i));
}
funcs[0]();  // 3 not 0!
funcs[1]();  // 3 not 1!
```

**How to fix:**
```javascript
// Before - var captures closure
for (var i = 0; i < 3; i++) {
  funcs.push(() => console.log(i));
}

// After - let captures value
for (let i = 0; i < 3; i++) {
  funcs.push(() => console.log(i));
}

// Or - Immediately Invoked Function
for (var i = 0; i < 3; i++) {
  (function(captured) {
    funcs.push(() => console.log(captured));
  })(i);
}
```

---

### 8. PROTOTYPE_POLLUTION

**What:** Accidentally modifying Object.prototype

**Example:**
```javascript
let obj = {};
obj.__proto__.evil = true;
let other = {};
console.log(other.evil);  // true - polluted!
```

**How to avoid:**
```javascript
// Use Object.create(null) to avoid prototype chain
let obj = Object.create(null);
obj.prop = "safe";  // Can't affect other objects

// Or use Map for key-value storage
let obj = new Map();
obj.set('key', 'value');
```

---

### 9. MEMORY_LEAK

**What:** Circular references preventing garbage collection

**Example:**
```javascript
let obj1 = { ref: null };
let obj2 = { ref: obj1 };
obj1.ref = obj2;
// Circular reference - garbage collector may not free
```

**When it matters:**
- Long-running processes
- Large object graphs
- Event listeners not removed

**How to avoid:**
```javascript
// Use WeakMap for caches
let cache = new WeakMap();
cache.set(obj, value);  // Auto-removed when obj collected

// Clean up references
obj.ref = null;  // Break cycle

// Remove event listeners
element.removeEventListener('click', handler);
```

---

### 10. FLOATING_POINT

**What:** IEEE 754 precision artifacts

**Example:**
```javascript
let x = 0.1 + 0.2;
console.log(x === 0.3);  // false!
console.log(x);  // 0.30000000000000004
```

**When it matters:**
- Financial calculations
- Physics simulations
- Precise comparisons

**How to fix:**
```javascript
// Before
if (x === 0.3) { ... }  // Unreliable

// After - Use integers
let cents = 10 + 20;  // Not dollars
let dollars = cents / 100;

// Or round for display
Math.round(x * 100) / 100

// Or use library
// npm install decimal.js
const Decimal = require('decimal.js');
let x = new Decimal(0.1).plus(0.2);
```

---

## Using Pattern Detection

```javascript
const { executeWithDebug } = require('./debug-engine.js');
const { BugPatternDetector } = require('./bug-patterns.js');

// Code with potential bug
const code = `
  let arr = [10, 20, 30];
  let alias = arr;
  alias.pop();  // Mutates arr too
`;

// Execute and analyze
const report = executeWithDebug(code);
const detector = new BugPatternDetector(report);
const patterns = detector.analyze();

// Print summary
console.log(detector.generateCombinedReport());

// Print detailed reports
patterns.forEach(p => {
  console.log(p.generateReport());
});
```

---

## Detection Confidence Levels

| Level | Meaning | Example |
|-------|---------|---------|
| 95%+ | Nearly certain | NULL_REFERENCE from TypeError |
| 80-94% | Very likely | OFF_BY_ONE with array bounds error |
| 70-79% | Likely | TYPE_MISMATCH with observed type change |
| 50-69% | Probable | RACE_CONDITION with async patterns |
| <50% | Possible | MEMORY_LEAK, FLOATING_POINT |

---

## Tips for Effective Pattern Use

1. **Run after exceptions** - Patterns are most useful when code fails
2. **Check severity first** - CRITICAL patterns need immediate attention
3. **Read root cause** - Explains the mechanism of the bug
4. **Use suggestions** - Specific fixes for each pattern
5. **Test after fixing** - Re-run debug to verify fix worked

