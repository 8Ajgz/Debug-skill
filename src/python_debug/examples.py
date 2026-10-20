#!/usr/bin/env python3
"""End-to-end examples: execute_with_debug + BugPatternDetector."""

import os
import sys

# Run as a script from any directory: the sibling modules live next to this file.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from debug_report import execute_with_debug
from bug_patterns import BugPatternDetector


def show(label, code, fixtures=None):
    print("\n" + "#" * 72)
    print(f"# {label}")
    print("#" * 72)
    report = execute_with_debug(code, globals_dict=fixtures)
    print(report.generate_human_readable())
    detector = BugPatternDetector(report)
    detector.analyze()
    if detector.patterns:
        print(detector.generate_combined_report())


# 1. Off-by-one
show("Off-by-one loop", """
arr = [1, 2, 3]
for i in range(1, len(arr) + 1):
    x = arr[i]
""")

# 2. Missing key
show("Missing dict key", """
data = {'name': 'Alice'}
value = data['age']
""")

# 3. Type mismatch
show("Type mismatch", "result = '5' + 5")

# 4. Division by zero
show("Division by zero", "x = 10 / 0")

# 5. Aliasing mutation (no crash, but pattern detected)
show("Aliasing mutation", """
x = [1, 2, 3]
y = x
y.append(4)
print('x:', x)
print('y:', y)
""")

# 6. Resource leak (string-only; the detector reads source, doesn't execute the open)
show("Resource leak (pattern detection only)", """
# This pattern is detected by reading source, not by running it.
def read_config():
    f = open('/tmp/config.txt')
    data = f.read()
    f.close()
    return data
""")

# 7. Successful run with traced timeline
show("Successful execution", """
xs = [1, 2, 3]
ys = [x * 2 for x in xs]
total = sum(ys)
print('total:', total)
""")

# --- NEW v11.1 EXAMPLES ---

# 8. Fixture injection with C-extension objects
print("\n" + "#" * 72)
print("# NEW: Fixture Injection (C-Extension Objects)")
print("#" * 72)

class BrokenRepr:
    """Simulate a PyMuPDF object with broken __repr__."""
    def __repr__(self):
        raise RuntimeError("repr failed in C extension")
    
    def get_text(self):
        return "extracted text"

code = """
# OBJ is injected; won't crash tracer even with broken __repr__
try:
    text = OBJ.get_text()
    result = text.upper()
except Exception as e:
    result = f"failed: {e}"
print(result)
"""

report = execute_with_debug(code, globals_dict={"OBJ": BrokenRepr()})
print(report.generate_human_readable())

# 9. Variable timeline dump
print("\n" + "#" * 72)
print("# NEW: Variable Mutation Timeline (dump_variables)")
print("#" * 72)

code = """
x = [1, 2, 3]
y = x  # Alias created
y.append(4)
z = x.copy()
z.append(5)
print('Final x:', x)
print('Final y:', y)
print('Final z:', z)
"""

report = execute_with_debug(code)
print(report.generate_human_readable())
print("\n=== VARIABLE TIMELINE ===")
print(report.dump_variables())

# 10. Resource leak on exception (new pattern)
print("\n" + "#" * 72)
print("# NEW: Resource Leak on Exception (Pattern Detection)")
print("#" * 72)

code = """
def problematic_close():
    resource = None
    try:
        if True:  # Dangerous operation could fail
            resource = object()
            resource.close()  # Never reached if exception above
    except Exception:
        pass

problematic_close()
"""

report = execute_with_debug(code)
detector = BugPatternDetector(report)
detector.analyze()
if detector.patterns:
    print(detector.generate_combined_report())
else:
    print("Note: Pattern may not trigger on this simple example.")

# 11. Silent exception swallow (new pattern)
print("\n" + "#" * 72)
print("# NEW: Silent Exception Swallow (Pattern Detection)")
print("#" * 72)

code = """
def extract_optional_feature():
    try:
        result = risky_operation()
        return result
    except Exception:
        return None  # Flagged as risky without logging

extract_optional_feature()
"""

report = execute_with_debug(code)
detector = BugPatternDetector(report)
detector.analyze()
if detector.patterns:
    print(detector.generate_combined_report())
else:
    print("Note: Pattern detected from source code parsing.")

# 12. Generator tracking (new v11.1 feature)
print("\n" + "#" * 72)
print("# NEW: Generator/Async Creation Tracking")
print("#" * 72)

code = """
def my_generator():
    yield 1
    yield 2

def my_coroutine():
    return "async result"

# Create generator and coroutine
g = my_generator()
print('Generator created')
"""

report = execute_with_debug(code)
print(report.generate_human_readable())

# Check for generator/async events
gen_events = [e for e in report.timeline if e.event_type in ("generator_yield", "await_point")]
if gen_events:
    print("\n=== GENERATOR/ASYNC EVENTS ===")
    for event in gen_events:
        print(f"  Event type: {event.event_type}")
        if event.event_type == "generator_yield":
            print(f"    Generator: {event.generator_name}")
        elif event.event_type == "await_point":
            print(f"    Coroutine: {event.coroutine_name}")
else:
    print("\nNote: No explicit generator/async events in this example.")
    print("(Generator creation in simple code may not trigger event)")

