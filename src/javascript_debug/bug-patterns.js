/**
 * bug-patterns.js: Recognize common bug patterns from a DebugReport.
 *
 * Detects: null references, type mismatches, off-by-one errors, aliasing mutations,
 * unhandled promises, and floating-point precision errors.
 */

const BugPatternType = {
  NULL_REFERENCE: 'null_reference',
  TYPE_MISMATCH: 'type_mismatch',
  OFF_BY_ONE: 'off_by_one_loop',
  ALIASING: 'aliasing_mutation',
  UNHANDLED_PROMISE: 'unhandled_promise_rejection',
  RACE_CONDITION: 'race_condition',
  CLOSURE_CAPTURE: 'closure_capture_issue',
  PROTOTYPE_POLLUTION: 'prototype_pollution',
  MEMORY_LEAK: 'memory_leak',
  FLOATING_POINT: 'floating_point_precision'
};

class DetectedPattern {
  constructor(options) {
    this.patternType = options.patternType;
    this.severity = options.severity;
    this.confidence = options.confidence;
    this.description = options.description;
    this.location = options.location;
    this.codeSnippet = options.codeSnippet;
    this.rootCause = options.rootCause;
    this.suggestion = options.suggestion;
    this.fixExample = options.fixExample;
  }

  generateReport() {
    const lines = [];
    lines.push('\n' + '='.repeat(70));
    lines.push(`BUG PATTERN DETECTED: ${this.patternType.toUpperCase()}`);
    lines.push('='.repeat(70));
    lines.push(`\nSeverity: ${this.severity.toUpperCase()}`);
    lines.push(`Confidence: ${Math.round(this.confidence * 100)}%`);
    
    if (this.location) {
      lines.push(`\nLocation: Line ${this.location}`);
    }
    
    lines.push(`\nDescription:\n  ${this.description}`);
    lines.push(`\nRoot Cause:`);
    
    for (const line of this.rootCause.split('\n')) {
      if (line) lines.push(`  ${line}`);
    }
    
    lines.push(`\nHow to Fix:`);
    for (const line of this.suggestion.split('\n')) {
      if (line) lines.push(`  ${line}`);
    }
    
    lines.push(`\nExample:`);
    for (const line of this.fixExample.split('\n')) {
      if (line) lines.push(`  ${line}`);
    }
    
    lines.push('\n' + '='.repeat(70));
    return lines.join('\n');
  }
}

class BugPatternDetector {
  constructor(debugReport) {
    this.report = debugReport;
    this.patterns = [];
  }

  analyze() {
    this.detectNullReferences();
    this.detectTypeMismatches();
    this.detectOffByOne();
    this.detectAliasingMutations();
    this.detectUnhandledPromises();
    this.detectFloatingPointErrors();
    
    return this.patterns;
  }

  detectNullReferences() {
    const events = this.report.timeline.filter(e => e.type === 'exception');
    
    for (const event of events) {
      if (event.exceptionType === 'TypeError' && event.message.includes('Cannot read')) {
        this.patterns.push(new DetectedPattern({
          patternType: BugPatternType.NULL_REFERENCE,
          severity: 'high',
          confidence: 0.95,
          description: 'Attempted to access property of null or undefined',
          location: event.lineIndex,
          rootCause: 'Variable was null or undefined when property access was attempted.',
          suggestion: 'Check if the variable is null/undefined before accessing properties:\n  Use optional chaining: obj?.property\n  Or guard clause: if (obj !== null) { ... }',
          fixExample: `// Before:\nlet value = obj.property;\n\n// After:\nlet value = obj?.property ?? defaultValue;`
        }));
      }
    }
  }

  detectTypeMismatches() {
    const timeline = this.report.timeline;
    
    for (let i = 0; i < timeline.length - 1; i++) {
      const event = timeline[i];
      
      if (event.type === 'variable') {
        const varHistory = this.report.variables.get(event.varName);
        if (varHistory && varHistory.length > 1) {
          const prev = varHistory[varHistory.length - 2];
          const curr = varHistory[varHistory.length - 1];
          
          const prevType = typeof prev.value;
          const currType = typeof curr.value;
          
          if (prevType !== currType && ['string', 'number', 'boolean'].includes(prevType)) {
            this.patterns.push(new DetectedPattern({
              patternType: BugPatternType.TYPE_MISMATCH,
              severity: 'medium',
              confidence: 0.7,
              description: `Variable '${event.varName}' changed type from ${prevType} to ${currType}`,
              location: event.lineIndex,
              rootCause: `Type coercion or implicit conversion changed the type.\n  Was: ${prev.value} (${prevType})\n  Now: ${curr.value} (${currType})`,
              suggestion: 'Use strict equality (===) and explicit type conversion:\n  const num = Number(str);\n  const bool = Boolean(value);',
              fixExample: `// Unexpected coercion:\nlet x = "5" + 3;  // "53" not 8\n\n// Better:\nlet x = Number("5") + 3;  // 8`
            }));
          }
        }
      }
    }
  }

  detectOffByOne() {
    for (const [varName, history] of this.report.variables) {
      if (Array.isArray(history[history.length - 1]?.value)) {
        const excEvents = this.report.timeline.filter(e => 
          e.type === 'exception' && 
          (e.message.includes('out of bounds') || e.message.includes('undefined'))
        );
        
        if (excEvents.length > 0) {
          for (const event of excEvents) {
            this.patterns.push(new DetectedPattern({
              patternType: BugPatternType.OFF_BY_ONE,
              severity: 'high',
              confidence: 0.8,
              description: `Array index out of bounds for '${varName}'`,
              location: event.lineIndex,
              rootCause: 'Loop boundaries or array access uses wrong index.\n  Common causes: Using < instead of <=, starting at 1 instead of 0, using length instead of length-1',
              suggestion: 'Check loop boundaries:\n  for (let i = 0; i < arr.length; i++)\n  Not: for (let i = 0; i <= arr.length; i++)',
              fixExample: `// Wrong:\nfor (let i = 0; i <= arr.length; i++) {\n  console.log(arr[i]);  // i = length causes undefined\n}\n\n// Right:\nfor (let i = 0; i < arr.length; i++) {\n  console.log(arr[i]);\n}`
            }));
          }
        }
      }
    }
  }

  detectAliasingMutations() {
    const aliases = this.report.getTrueAliases();
    
    if (aliases.size > 0) {
      for (const [refId, varNames] of aliases) {
        const mutations = varNames.map(v => this.report.getVariableMutations(v)).flat();
        
        if (mutations.length > 1) {
          this.patterns.push(new DetectedPattern({
            patternType: BugPatternType.ALIASING,
            severity: 'high',
            confidence: 0.95,
            description: `Variables ${varNames.join(', ')} share the same object and are mutated`,
            location: mutations[mutations.length - 1].lineIndex,
            rootCause: `Multiple variables reference the same object.\n  When one is mutated, all aliases see the change.\n  Variables: ${varNames.join(', ')}`,
            suggestion: 'Use immutable updates or create copies:\n  const copy = [...original];\n  const newObj = { ...obj, property: newValue };',
            fixExample: `// Problem:\nlet arr1 = [1, 2, 3];\nlet arr2 = arr1;\narr2.push(4);  // arr1 is also modified!\n\n// Solution:\nlet arr2 = [...arr1];  // Deep copy\narr2.push(4);  // arr1 unchanged`
          }));
        }
      }
    }
  }

  detectUnhandledPromises() {
    for (const promise of this.report.promises) {
      if (promise.status === 'rejected') {
        this.patterns.push(new DetectedPattern({
          patternType: BugPatternType.UNHANDLED_PROMISE,
          severity: 'critical',
          confidence: 0.9,
          description: `Promise ${promise.id} was rejected but may be unhandled`,
          location: promise.createdAt,
          rootCause: `A Promise was rejected without a .catch() or try/catch in async function.\n  Reason: ${promise.reason}`,
          suggestion: 'Always handle Promise rejections:\n  promise.catch(err => { ... })\n  Or use try/catch with await:\n  try { await promise; } catch (e) { ... }',
          fixExample: `// Unhandled:\nlet p = somePromise();\n\n// Handled:\nlet p = somePromise().catch(err => console.error(err));\n\n// Or with async/await:\nasync function main() {\n  try {\n    await somePromise();\n  } catch (err) {\n    console.error(err);\n  }\n}`
        }));
      }
    }
  }

  detectFloatingPointErrors() {
    for (const [varName, history] of this.report.variables) {
      for (const entry of history) {
        if (typeof entry.value === 'number' && !Number.isInteger(entry.value)) {
          const str = String(entry.value);
          if (str.includes('e-') || (str.match(/\./g) || []).length > 1) {
            this.patterns.push(new DetectedPattern({
              patternType: BugPatternType.FLOATING_POINT,
              severity: 'low',
              confidence: 0.6,
              description: `Variable '${varName}' has floating-point precision artifacts`,
              location: entry.lineIndex,
              rootCause: 'Floating-point arithmetic can introduce precision errors.\n  Example: 0.1 + 0.2 === 0.30000000000000004 (not 0.3)',
              suggestion: 'For monetary values, use integers (cents) or Decimal library:\n  Use Math.round() for display:\n  console.log(Math.round(x * 100) / 100);',
              fixExample: `// Problem:\nlet total = 0.1 + 0.2;\nconsole.log(total === 0.3);  // false!\n\n// Solution:\nlet cents = 10 + 20;  // Use integers\nlet dollars = cents / 100;  // 0.30`
            }));
          }
        }
      }
    }
  }

  generateCombinedReport() {
    const lines = [];
    lines.push('='.repeat(70));
    lines.push(`BUG PATTERN ANALYSIS REPORT`);
    lines.push('='.repeat(70));
    lines.push(`\nPatterns Found: ${this.patterns.length}`);
    
    if (this.patterns.length === 0) {
      lines.push('\n✓ No obvious patterns detected!');
    } else {
      const bySeverity = {};
      for (const pattern of this.patterns) {
        if (!bySeverity[pattern.severity]) {
          bySeverity[pattern.severity] = [];
        }
        bySeverity[pattern.severity].push(pattern);
      }
      
      for (const severity of ['critical', 'high', 'medium', 'low']) {
        if (bySeverity[severity]) {
          lines.push(`\n${severity.toUpperCase()} (${bySeverity[severity].length}):`);
          for (const pattern of bySeverity[severity]) {
            lines.push(`  - ${pattern.patternType}: ${pattern.description}`);
          }
        }
      }
    }
    
    lines.push('\n' + '='.repeat(70));
    return lines.join('\n');
  }
}

module.exports = {
  BugPatternDetector,
  DetectedPattern,
  BugPatternType
};
