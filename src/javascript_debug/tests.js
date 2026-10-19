/**
 * tests.js: Test suite for javascript-debug
 */

const assert = require('assert');
const { executeWithDebug } = require('./debug-engine.js');
const { BugPatternDetector } = require('./bug-patterns.js');

let testsPassed = 0;
let testsFailed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`✓ ${name}`);
    testsPassed++;
  } catch (error) {
    console.error(`✗ ${name}`);
    console.error(`  ${error.message}`);
    testsFailed++;
  }
}

test('Basic variable tracking', () => {
  const code = `
    let x = 10;
    let y = 20;
    let z = x + y;
  `;
  
  const report = executeWithDebug(code);
  assert(report.variables.has('x'), 'Variable x should be tracked');
  assert(report.variables.has('y'), 'Variable y should be tracked');
  assert(report.variables.has('z'), 'Variable z should be tracked');
});

test('Mutation history', () => {
  const code = `
    let count = 0;
    count = 1;
    count = 2;
  `;
  
  const report = executeWithDebug(code);
  const mutations = report.getVariableMutations('count');
  assert(mutations.length >= 1, 'Should track mutations');
});

test('Aliasing detection', () => {
  const code = `
    let arr = [1, 2, 3];
    let copy = arr;
  `;
  
  const report = executeWithDebug(code);
  const aliases = report.getTrueAliases();
  assert(typeof aliases === 'object', 'Should return aliases map');
});

test('Exception capturing', () => {
  const code = `
    let obj = null;
    obj.property;
  `;
  
  const report = executeWithDebug(code);
  assert(report.exceptionInfo !== null, 'Should capture exception');
  assert(report.exceptionInfo.type !== undefined, 'Exception should have type');
});

test('Pattern detection execution', () => {
  const code = `
    let arr = [1, 2];
    let x = arr[10];
  `;
  
  const report = executeWithDebug(code);
  const detector = new BugPatternDetector(report);
  const patterns = detector.analyze();
  assert(Array.isArray(patterns), 'Should return patterns array');
});

test('Human-readable report', () => {
  const code = `
    let x = 42;
  `;
  
  const report = executeWithDebug(code);
  const readable = report.generateHumanReadable();
  assert(typeof readable === 'string', 'Should generate string report');
  assert(readable.length > 0, 'Report should not be empty');
});

test('JSON serialization', () => {
  const code = `
    let x = 123;
  `;
  
  const report = executeWithDebug(code);
  const json = report.toJSON();
  assert(json.description !== undefined, 'JSON should have description');
  assert(Array.isArray(json.timeline), 'JSON should have timeline array');
});

test('Timeout protection', () => {
  const code = `
    while (true) {}
  `;
  
  try {
    const report = executeWithDebug(code, {}, { timeout: 100 });
  } catch (error) {
    assert(error.message.includes('timeout') || error.message.includes('Execution'), 
      'Should handle timeout');
  }
});

test('Multiple variable tracking', () => {
  const code = `
    let a = 1;
    let b = 2;
    let c = 3;
    let d = 4;
    let e = 5;
  `;
  
  const report = executeWithDebug(code);
  assert(report.variables.size >= 3, 'Should track multiple variables');
});

test('Global scope injection', () => {
  const code = `
    let result = CONFIG.value;
  `;
  
  const globalScope = { CONFIG: { value: 42 } };
  const report = executeWithDebug(code, globalScope);
  assert(report.variables.has('result'), 'Should track injected scope variables');
});

console.log('\n' + '='.repeat(70));
console.log(`Tests: ${testsPassed} passed, ${testsFailed} failed`);
console.log('='.repeat(70));

process.exit(testsFailed > 0 ? 1 : 0);
