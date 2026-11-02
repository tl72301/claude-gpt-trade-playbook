"""Seed solver, revised in generation 1.

Changes: multiple attempts with self-checking against the shown examples, feedback that
includes the previous code and the failing case, and a guard for replies that lack f.
"""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the exact rule and check it against every example, including edge cases such as "
    "empty lists, negative numbers, and output length. The function must be named f."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Before coding, state the rule per element, per position, or per window, and verify it on every example.",
    "Prefer simple rules. Do not special-case the examples unless no general rule fits.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if re.search(r"def\s+f\s*\(", block):
            return block
    if blocks:
        return blocks[-1]
    match = re.search(r"def\s+f\s*\(.*", text, re.DOTALL)
    return match.group(0) if match else text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block."
    )
    prompt = base
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not re.search(r"def\s+f\s*\(", code):
            prompt = (
                base
                + "\n\nYour previous reply did not define a function named f. "
                "Reply with a complete `def f(xs):` in one ```python block."
            )
            continue
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        first = failed[0]
        prompt = (
            base
            + f"\n\nPrevious attempt:\n```python\n{code}```\n"
            f"It failed on f({first['input']}): it returned {first['actual']}, "
            f"expected {first['expected']}. Find one general rule that explains all examples "
            "and fix the code. Return only the corrected code in one ```python block."
        )
    return code
