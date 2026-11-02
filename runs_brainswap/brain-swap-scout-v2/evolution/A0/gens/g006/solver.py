"""Solver v2. Checks its own code against the shown examples and retries with feedback."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Find the simplest rule that explains every example, and check edge cases "
    "such as empty lists, negative numbers and outputs whose length depends on the input."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Define a top-level function named f that takes one argument xs.",
    "Use only the standard library. Do not read input or print anything.",
    "Verify your rule by hand against at least two examples before answering.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if "def f" in block:
            return block
    return blocks[-1] if blocks else text


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
        if "def f" not in code:
            prompt = (
                base
                + "\n\nYour last reply did not define a function named f. "
                "Reply with a complete top-level def f(xs) in one ```python block."
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
            + f"\n\nPrevious attempt:\n```python\n{code}\n```\n"
            + f"It was wrong: f({first['input']}) returned {first['actual']}, "
            + f"expected {first['expected']}. Find a rule that fits all the examples "
            + "and rewrite f. Return only the code in one ```python block."
        )
    return code
