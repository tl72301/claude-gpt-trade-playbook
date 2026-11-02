"""Solver: multi-attempt with check feedback and hints."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Study the examples carefully; the rule may combine steps such as sliding windows, "
    "prefix sums, filtering, sorting, pairwise differences, or index-dependent arithmetic.",
    "Output length may differ from input length (e.g. windows of size k give len-k+1 items).",
    "The function must generalize to hidden inputs, including empty lists and negatives; avoid hardcoding.",
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
        + "First think briefly about the rule, verify it against each example mentally, "
        "then give the code in one ```python block."
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
            f"{first['actual']}, expected {first['expected']}. Reconsider the rule "
            "from scratch and fix it."
        )
    return code
