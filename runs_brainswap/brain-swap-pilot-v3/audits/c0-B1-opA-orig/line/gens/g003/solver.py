"""Solver: multiple attempts with check feedback, robust code extraction."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "The function must be named exactly `f` and take one argument `xs`.",
    "Look for a general rule (windows, pairs, prefix sums, filtering, sorting); do not hard-code examples.",
    "Handle short or empty lists without raising errors.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    prompt = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Think briefly about the rule first, then return the final code in one ```python block."
    )
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if "def f" not in code:
            prompt += "\n\nYour reply had no `def f(xs):`. Return a complete function named f in a ```python block."
            continue
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        first = failed[0]
        prompt += (
            f"\n\nAttempt {attempt + 1} was wrong: f({first['input']}) returned "
            f"{first['actual']}, expected {first['expected']}. Rethink the rule and fix it."
        )
    return code
