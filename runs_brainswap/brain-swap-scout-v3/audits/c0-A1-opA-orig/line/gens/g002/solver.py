"""Seed solver, revised: checks its own code against the shown examples and retries with concrete failures."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the exact rule. Check empty lists, negatives, zeros and single-element inputs. "
    "Never hard-code outputs for the shown examples."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Try a per-element rule first, then a rule that depends on index or on a running (prefix) value, then a filter or pairing rule.",
    "Use only the Python standard library and define exactly def f(xs).",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
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
    best_code, best_failed = "", None
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
            return best_code or code
        failed = [r for r in report if not r["passed"]]
        if best_failed is None or len(failed) < best_failed:
            best_code, best_failed = code, len(failed)
        if not failed:
            return code
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        ]
        prompt = (
            base
            + f"\n\nYour previous attempt was:\n```python\n{code}\n```\n"
            + "It failed on:\n" + "\n".join(lines)
            + "\nFind the rule that explains all examples, then rewrite the function. "
            + "Return only the code in one ```python block."
        )
    return best_code
