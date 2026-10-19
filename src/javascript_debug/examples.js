/**
 * examples.js: Working examples for javascript-debug
 */

const { executeWithDebug } = require('./debug-engine.js');
const { BugPatternDetector } = require('./bug-patterns.js');

function exampleBasicTracking() {
  console.log('\n' + '='.repeat(70));
  console.log('Example 1: Basic Variable Tracking');
  console.log('='.repeat(70));
  
  const code = `
    let x = 10;
    let y = 20;
    let z = x + y;
    x = 50;
  `;
  
  const report = executeWithDebug(code);
  console.log(report.generateHumanReadable());
}

function exampleAliasing() {
  console.log('\n' + '='.repeat(70));
  console.log('Example 2: Aliasing Detection');
  console.log('='.repeat(70));
  
  const code = `
    let arr = [1, 2, 3];
    let copy = arr;
    copy.push(4);
  `;
  
  const report = executeWithDebug(code);
  console.log('Aliases:', report.getTrueAliases());
  console.log('Variables:', report.dumpVariables());
}

function exampleException() {
  console.log('\n' + '='.repeat(70));
  console.log('Example 3: Exception Handling');
  console.log('='.repeat(70));
  
  const code = `
    let obj = null;
    let prop = obj.property;
  `;
  
  const report = executeWithDebug(code);
  console.log(report.generateHumanReadable());
  
  if (report.exceptionInfo) {
    console.log('\nCaught Exception:');
    console.log('  Type:', report.exceptionInfo.type);
    console.log('  Message:', report.exceptionInfo.message);
  }
}

function examplePatterns() {
  console.log('\n' + '='.repeat(70));
  console.log('Example 4: Pattern Detection');
  console.log('='.repeat(70));
  
  const code = `
    let arr = [10, 20, 30];
    for (let i = 0; i <= arr.length; i++) {
      let val = arr[i];
    }
  `;
  
  const report = executeWithDebug(code);
  const detector = new BugPatternDetector(report);
  const patterns = detector.analyze();
  
  console.log(detector.generateCombinedReport());
  
  for (const pattern of patterns) {
    console.log(pattern.generateReport());
  }
}

function exampleTypeErrors() {
  console.log('\n' + '='.repeat(70));
  console.log('Example 5: Type Error Detection');
  console.log('='.repeat(70));
  
  const code = `
    let x = "5";
    let y = x + 3;
    let z = Number(x) + 3;
  `;
  
  const report = executeWithDebug(code);
  const detector = new BugPatternDetector(report);
  const patterns = detector.analyze();
  
  console.log(report.generateHumanReadable());
  console.log(detector.generateCombinedReport());
}

if (require.main === module) {
  try {
    exampleBasicTracking();
    exampleAliasing();
    exampleException();
    examplePatterns();
    exampleTypeErrors();
  } catch (error) {
    console.error('Example error:', error);
  }
}

module.exports = {
  exampleBasicTracking,
  exampleAliasing,
  exampleException,
  examplePatterns,
  exampleTypeErrors
};
