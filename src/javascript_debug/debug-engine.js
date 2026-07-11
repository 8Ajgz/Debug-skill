/**
 * debug-engine.js: Execute and debug JavaScript code with full execution visibility.
 *
 * Features:
 *   - Line-by-line variable tracking via code instrumentation
 *   - Alias detection (variables sharing the same object reference)
 *   - Mutation detection (state changing under aliased references)
 *   - Exception capture with frame locals and source line
 *   - JSON and human-readable reports
 *   - Promise and async/await tracking
 *
 * Usage:
 *     const { executeWithDebug } = require('./debug-engine.js');
 *
 *     const code = `
 *     let x = [1, 2, 3];
 *     let y = x;
 *     y.push(4);
 *     let z = x[10];
 *     `;
 *
 *     const report = executeWithDebug(code);
 *     console.log(report.generateHumanReadable());
 */

class DebugReport {
  constructor(description = "execution trace") {
    this.description = description;
    this.timeline = [];
    this.variables = new Map();
    this.callStack = [];
    this.promises = [];
    this.asyncEvents = [];
    this.exceptionInfo = null;
    this.exceptionFrame = null;
    this.exceptionLine = null;
    this.startTime = Date.now();
    this.endTime = null;
  }

  logVariable(lineIndex, varName, value, metadata = {}) {
    if (!this.variables.has(varName)) {
      this.variables.set(varName, []);
    }
    
    this.variables.get(varName).push({
      lineIndex,
      value: this.truncateValue(value),
      refId: this.getRefId(value),
      timestamp: Date.now() - this.startTime,
      ...metadata
    });

    this.timeline.push({
      type: 'variable',
      lineIndex,
      varName,
      value: this.truncateValue(value),
      timestamp: Date.now() - this.startTime,
      callStack: [...this.callStack]
    });

    // instrumentCode() rewrites `let x = <rhs>;` into
    // `let x = __report.logVariable(0, 'x', (<rhs>));`, so this method's
    // return value becomes the actual value assigned to `x`. Previously
    // this had no return statement (implicitly returned undefined),
    // meaning every single instrumented variable was silently rebound to
    // undefined regardless of its real value -- confirmed by direct
    // execution while fixing instrumentCode()'s separate unclosed-paren
    // bug (see instrumentCode() comment), not caught by review alone
    // since without the paren fix this line never even ran.
    return value;
  }

  logFunctionCall(lineIndex, functionName, args = {}) {
    this.callStack.push(functionName);
    this.timeline.push({
      type: 'call',
      lineIndex,
      functionName,
      args,
      timestamp: Date.now() - this.startTime,
      depth: this.callStack.length
    });
  }

  logFunctionReturn(lineIndex, functionName, returnValue) {
    this.callStack.pop();
    this.timeline.push({
      type: 'return',
      lineIndex,
      functionName,
      returnValue: this.truncateValue(returnValue),
      timestamp: Date.now() - this.startTime,
      depth: this.callStack.length
    });
  }

  logPromiseCreated(lineIndex, promiseId, executor) {
    this.promises.push({
      id: promiseId,
      createdAt: lineIndex,
      status: 'pending',
      result: null,
      reason: null
    });

    this.timeline.push({
      type: 'promise_created',
      lineIndex,
      promiseId,
      timestamp: Date.now() - this.startTime
    });
  }

  logPromiseResolved(lineIndex, promiseId, value) {
    const promise = this.promises.find(p => p.id === promiseId);
    if (promise) {
      promise.status = 'resolved';
      promise.result = this.truncateValue(value);
    }

    this.timeline.push({
      type: 'promise_resolved',
      lineIndex,
      promiseId,
      value: this.truncateValue(value),
      timestamp: Date.now() - this.startTime
    });
  }

  logPromiseRejected(lineIndex, promiseId, reason) {
    const promise = this.promises.find(p => p.id === promiseId);
    if (promise) {
      promise.status = 'rejected';
      promise.reason = String(reason);
    }

    this.timeline.push({
      type: 'promise_rejected',
      lineIndex,
      promiseId,
      reason: String(reason),
      timestamp: Date.now() - this.startTime
    });
  }

  logAsyncPoint(lineIndex, functionName, state = 'created') {
    this.asyncEvents.push({
      lineIndex,
      functionName,
      state,
      timestamp: Date.now() - this.startTime
    });

    this.timeline.push({
      type: 'async_point',
      lineIndex,
      functionName,
      state,
      timestamp: Date.now() - this.startTime
    });
  }

  captureException(error, lineIndex, locals) {
    this.exceptionInfo = {
      type: error.constructor.name,
      message: error.message,
      stack: error.stack
    };
    this.exceptionFrame = locals;
    this.exceptionLine = lineIndex;

    this.timeline.push({
      type: 'exception',
      lineIndex,
      exceptionType: error.constructor.name,
      message: error.message,
      locals: Object.fromEntries(
        Object.entries(locals).map(([k, v]) => [k, this.truncateValue(v)])
      ),
      timestamp: Date.now() - this.startTime
    });
  }

  getRefId(value) {
    if (value === null || value === undefined) return 'null';
    if (typeof value !== 'object') return typeof value;
    
    if (!value.__debugRefId) {
      value.__debugRefId = 'ref_' + Math.random().toString(36).substring(7);
    }
    return value.__debugRefId;
  }

  truncateValue(value) {
    if (value === null || value === undefined) return value;
    
    const str = String(value);
    if (str.length > 500) {
      return str.substring(0, 500) + '... (truncated)';
    }
    return value;
  }

  getTrueAliases() {
    const refMap = new Map();
    
    for (const [varName, history] of this.variables) {
      if (history.length === 0) continue;
      
      const refId = history[history.length - 1].refId;
      if (refId !== 'null' && typeof refId === 'string' && refId.startsWith('ref_')) {
        if (!refMap.has(refId)) {
          refMap.set(refId, []);
        }
        refMap.get(refId).push(varName);
      }
    }

    const result = new Map();
    for (const [ref, vars] of refMap) {
      if (vars.length > 1) {
        result.set(ref, vars);
      }
    }
    return result;
  }

  getVariableMutations(varName) {
    if (!this.variables.has(varName)) return [];
    
    const history = this.variables.get(varName);
    return history.map((entry, idx) => ({
      lineIndex: entry.lineIndex,
      value: entry.value,
      timestamp: entry.timestamp,
      index: idx
    }));
  }

  getCallStackAt(lineIndex) {
    for (let i = this.timeline.length - 1; i >= 0; i--) {
      if (this.timeline[i].lineIndex === lineIndex && this.timeline[i].callStack) {
        return this.timeline[i].callStack;
      }
    }
    return [];
  }

  getPromiseEvents() {
    return this.timeline.filter(e => e.type.includes('promise'));
  }

  getAsyncEvents() {
    return this.asyncEvents;
  }

  getTimeline() {
    return this.timeline;
  }

  generateHumanReadable() {
    const lines = [];
    lines.push('='.repeat(70));
    lines.push(`DEBUG REPORT: ${this.description}`);
    lines.push('='.repeat(70));
    lines.push(`Duration: ${this.endTime - this.startTime}ms`);
    lines.push(`Events: ${this.timeline.length}`);
    lines.push('');

    lines.push('TIMELINE:');
    lines.push('-'.repeat(70));
    
    for (let i = 0; i < Math.min(this.timeline.length, 50); i++) {
      const event = this.timeline[i];
      switch (event.type) {
        case 'variable':
          lines.push(`[${i}] ${event.varName} = ${event.value}`);
          break;
        case 'call':
          lines.push(`[${i}] → ${event.functionName}()`);
          break;
        case 'return':
          lines.push(`[${i}] ← ${event.functionName}() returned ${event.returnValue}`);
          break;
        case 'exception':
          lines.push(`[${i}] ✗ ${event.exceptionType}: ${event.message}`);
          break;
        case 'promise_created':
          lines.push(`[${i}] Promise created: ${event.promiseId}`);
          break;
        case 'promise_resolved':
          lines.push(`[${i}] Promise resolved: ${event.promiseId} = ${event.value}`);
          break;
        case 'async_point':
          lines.push(`[${i}] await ${event.functionName} [${event.state}]`);
          break;
      }
    }

    if (this.timeline.length > 50) {
      lines.push(`... and ${this.timeline.length - 50} more events`);
    }

    lines.push('');
    lines.push('VARIABLES:');
    lines.push('-'.repeat(70));
    
    for (const [varName, history] of this.variables) {
      if (history.length > 0) {
        const latest = history[history.length - 1];
        lines.push(`${varName}: ${latest.value} (${history.length} updates)`);
      }
    }

    if (this.exceptionInfo) {
      lines.push('');
      lines.push('EXCEPTION:');
      lines.push('-'.repeat(70));
      lines.push(`Type: ${this.exceptionInfo.type}`);
      lines.push(`Message: ${this.exceptionInfo.message}`);
      lines.push(`Frame:`, JSON.stringify(this.exceptionFrame, null, 2));
    }

    lines.push('');
    lines.push('='.repeat(70));
    return lines.join('\n');
  }

  dumpVariables() {
    const result = {};
    for (const [varName, history] of this.variables) {
      if (history.length > 0) {
        result[varName] = {
          current: history[history.length - 1].value,
          mutations: history.length,
          history: history.map(h => ({ line: h.lineIndex, value: h.value }))
        };
      }
    }
    return result;
  }

  toJSON() {
    return {
      description: this.description,
      duration: this.endTime - this.startTime,
      timeline: this.timeline,
      variables: Object.fromEntries(this.variables),
      promises: this.promises,
      asyncEvents: this.asyncEvents,
      exceptionInfo: this.exceptionInfo
    };
  }
}

class TrackedAsyncContext {
  constructor(functionName, report = null) {
    this.functionName = functionName;
    this.report = report;
    this.startTime = null;
    this.endTime = null;
  }

  async run(asyncFn) {
    this.startTime = Date.now();
    if (this.report) {
      this.report.logAsyncPoint(0, this.functionName, 'created');
    }

    try {
      const result = await asyncFn();
      if (this.report) {
        this.report.logAsyncPoint(0, this.functionName, 'resolved');
      }
      return result;
    } catch (error) {
      if (this.report) {
        this.report.logAsyncPoint(0, this.functionName, 'rejected');
      }
      throw error;
    } finally {
      this.endTime = Date.now();
    }
  }
}

function executeWithDebug(code, globalScope = {}, options = {}) {
  const {
    traceVariables = true,
    maxTimelineSize = 1000,
    timeout = 5000
  } = options;

  const report = new DebugReport('JavaScript execution');
  let timeoutHandle = null;

  try {
    const instrumentedCode = instrumentCode(code, report);

    const fullScope = {
      ...globalScope,
      __report: report,
      __debugCallStack: [],
      Promise: createInstrumentedPromise(Promise, report),
      console: {
        log: (...args) => console.log(...args),
        error: (...args) => console.error(...args),
        warn: (...args) => console.warn(...args)
      }
    };

    if (timeout) {
      timeoutHandle = setTimeout(() => {
        throw new Error(`Execution timeout after ${timeout}ms`);
      }, timeout);
    }

    const fn = new Function(...Object.keys(fullScope), instrumentedCode);
    fn(...Object.values(fullScope));

  } catch (error) {
    report.captureException(error, 0, Object.fromEntries(
      [...report.variables].map(([k, v]) => [k, v.length > 0 ? v[v.length - 1].value : undefined])
    ));
  } finally {
    if (timeoutHandle) clearTimeout(timeoutHandle);
    report.endTime = Date.now();
  }

  return report;
}

function instrumentCode(code, report) {
  // Previous implementation: a single global regex replace that turned
  // `let x = <rhs>;` into `let x = __report.logVariable(0, 'x', <rhs>;`
  // -- opening a call to logVariable() but never closing it. This was a
  // 100%-reproducible syntax error for every single variable
  // declaration in any code passed to executeWithDebug() (confirmed by
  // direct execution while fixing the Python orchestrator around this
  // file -- every declaration failed with "missing ) after argument
  // list"), silently swallowed by executeWithDebug()'s catch block into
  // a captured "exception" rather than ever actually running.
  //
  // Fixed by scanning for the real end of each declaration's RHS
  // (respecting string/template-literal contents and nested brackets,
  // so semicolons inside a string or a nested call don't terminate the
  // statement early) and wrapping exactly that span.
  const declRegex = /\b(?:let|const|var)\s+(\w+)\s*=\s*/g;
  let result = '';
  let lastIndex = 0;
  let match;

  while ((match = declRegex.exec(code)) !== null) {
    const varName = match[1];
    const rhsStart = match.index + match[0].length;
    const stmtEnd = findStatementEnd(code, rhsStart);

    result += code.slice(lastIndex, match.index);
    result += `let ${varName} = __report.logVariable(0, '${varName}', (`;
    result += code.slice(rhsStart, stmtEnd);
    result += '))';

    lastIndex = stmtEnd;
    declRegex.lastIndex = stmtEnd;
  }
  result += code.slice(lastIndex);

  return result;
}

function findStatementEnd(code, start) {
  // Returns the index of the statement-terminating ';' (or end of
  // code/enclosing block) for the RHS expression beginning at `start`,
  // tracking bracket/paren/brace depth and string/template-literal
  // contents so semicolons or brackets inside those don't count.
  let depth = 0;
  let inString = null; // one of ' " ` while inside a string/template literal
  for (let i = start; i < code.length; i++) {
    const c = code[i];
    if (inString) {
      if (c === '\\') { i++; continue; }
      if (c === inString) inString = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { inString = c; continue; }
    if (c === '(' || c === '[' || c === '{') { depth++; continue; }
    if (c === ')' || c === ']' || c === '}') {
      if (depth === 0) return i; // closing something that opened before `start` (e.g. end of an enclosing block) -- treat as statement end
      depth--;
      continue;
    }
    if (c === ';' && depth === 0) return i;
  }
  return code.length;
}

function createInstrumentedPromise(OriginalPromise, report) {
  return class InstrumentedPromise extends OriginalPromise {
    constructor(executor) {
      let promiseId = 'promise_' + Math.random().toString(36).substring(7);
      report.logPromiseCreated(0, promiseId, executor);

      super((resolve, reject) => {
        executor(
          (value) => {
            report.logPromiseResolved(0, promiseId, value);
            resolve(value);
          },
          (reason) => {
            report.logPromiseRejected(0, promiseId, reason);
            reject(reason);
          }
        );
      });
    }
  };
}

module.exports = {
  DebugReport,
  TrackedAsyncContext,
  executeWithDebug
};
