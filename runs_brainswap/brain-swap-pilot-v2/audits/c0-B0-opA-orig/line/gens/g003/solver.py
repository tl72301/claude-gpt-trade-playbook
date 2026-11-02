"""Seed solver, revised: repair loop driven by the shown-example checker."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Before coding, consider the common rule families: per-element arithmetic, "
    "filtering by a predicate, sorting, prefix sums, adjacent differences, "
    "index-based rules, counting, reversal, and output-length rules.",
    "Verify the rule against EVERY example, including the output length and any empty outputs.",
    "Prefer the simplest rule that fits all examples. Do not hard-code example values.",
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
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        ]
        prompt = (
            base
            + "\n\nYour previous attempt was:\n```python\n" + code + "```\n"
            + "It failed on:\n" + "\n".join(lines)
            + "\nFind the rule that explains ALL examples and rewrite f. Return only the code in one ```python block."
        )
    return code
