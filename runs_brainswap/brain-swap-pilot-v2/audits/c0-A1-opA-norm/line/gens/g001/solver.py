"""Seed solver, revised in generation 1.

Changes: uses api.check feedback over several attempts, feeds back all failing
examples (not just the first), and rejects replies that do not define f.
"""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Work out the rule by comparing each output element with the input elements "
    "(position, neighbours, running sums, counts, sorting, filtering, pairwise sums).",
    "The output length may differ from the input length. Check it on every example.",
    "The function must be named f and take one list argument xs.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for b in reversed(blocks):
        if "def f" in b:
            return b
    if "def f" in text:
        return text
    return ""


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']}) == {ex['output']}" for ex in task["examples"]
    )
    prompt = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n"
        + examples
        + "\n\n"
        + "".join(f"Hint: {h}\n" for h in HINTS)
        + "Return only the code in one ```python block."
    )
    code = ""
    for i in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not code:
            prompt += "\n\nYour reply had no def f(xs). Reply with a ```python block defining f."
            continue
        if not USE_CHECK:
            return code
        try:
            results = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [r for r in results if not r["passed"]]
        if not failed:
            return code
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        ]
        prompt += (
            f"\n\nAttempt {i + 1} was wrong on {len(failed)} example(s):\n"
            + "\n".join(lines)
            + "\nRethink the rule from scratch against all examples and fix it."
        )
    return code or "def f(xs):\n    return list(xs)\n"
