"""Solver with multiple attempts, check-based feedback, and hints."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Outputs are often shorter than inputs: consider sliding windows (pairs of adjacent elements) or prefix/running operations.",
    "Consider adjacent-pair functions such as sign of difference, comparisons, sums or differences mod some number.",
    "Infer the rule from ALL examples, and verify mentally against each example before answering.",
    "Handle edge cases such as empty or length-1 inputs by returning [].",
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
        + "Think briefly about the rule, then return the final code in one ```python block."
    )
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
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
        prompt += (
            f"\n\nAttempt {attempt + 1} was wrong: f({first['input']}) returned "
            f"{first['actual']}, expected {first['expected']}. Rethink the rule "
            "from all examples and fix it."
        )
    return code
