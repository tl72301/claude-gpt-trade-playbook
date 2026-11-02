"""Solver: multiple attempts with check feedback, and hints about common patterns."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Outputs are often shorter than inputs: look at sliding windows of size 2 or 3 over adjacent elements (e.g. pairwise sums, differences, comparisons, counts).",
    "Check the output length against the input length (len-1, len-2, etc.) to infer the window size.",
    "Test each hypothesis against ALL examples mentally before answering. Short lists may give an empty list.",
    "The code must define exactly `def f(xs):` at top level and return a list of ints.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1]
    if "def f" in text:
        return text
    return text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    prompt = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below. Think briefly about the rule "
        "(it should generalize to unseen inputs), then give the code.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "End with the code in one ```python block."
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
            return code
        except Exception as e:
            prompt += f"\n\nAttempt {attempt + 1} crashed: {e}. Fix it."
            continue
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        first = failed[0]
        prompt += (
            f"\n\nAttempt {attempt + 1} was wrong: f({first['input']}) returned "
            f"{first['actual']}, expected {first['expected']}. Reconsider the rule and fix it."
        )
    return code
