"""Solver generation 2: check-driven repair loop with generalization hints."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Find the general rule behind the examples; do not hard-code the examples."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Look for the simplest rule that explains every example, then verify it by hand on each one.",
    "Handle edge cases generally: empty lists, a single element, all-negative or all-zero values, repeated values.",
    "Return a new list; do not mutate the input.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        for b in reversed(blocks):
            if "def f" in b:
                return b
        return blocks[-1]
    return text


def build_prompt(task):
    examples = "\n".join(f"f({e['input']}) == {e['output']}" for e in task["examples"])
    hints = "".join(f"Hint: {h}\n" for h in HINTS)
    return (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below. It must generalize to unseen inputs.\n\n"
        + examples
        + "\n\n"
        + hints
        + "Return only the code in one ```python block."
    )


def solve(task, api):
    prompt = build_prompt(task)
    feedback = ""
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not USE_CHECK:
            return code
        try:
            results = api.check(code)
        except api.BudgetExceeded:
            return code
        except Exception:
            return code
        failing = [r for r in results if not r["passed"]]
        if not failing:
            return code
        bad = failing[0]
        feedback = (
            "\n\nYour previous attempt was:\n```python\n" + code + "\n```\n"
            f"It failed: f({bad['input']}) returned {bad['actual']}, "
            f"expected {bad['expected']}. Discard the flawed idea, identify the general "
            "rule that fits all examples, and rewrite f from scratch in one ```python block."
        )
    return code
