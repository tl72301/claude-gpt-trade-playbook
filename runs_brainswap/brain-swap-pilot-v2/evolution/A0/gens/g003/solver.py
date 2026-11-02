"""Seed solver, revised: robust extraction and check-driven repair."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Output must be a list of ints. Return [] when the rule produces nothing.",
    "Check that the output length matches the input length in every example, and handle negative numbers.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    blocks = [b for b in blocks if "def f" in b]
    if blocks:
        return blocks[-1]
    match = re.search(r"(def f\s*\(.*)", text, re.DOTALL)
    if match:
        return match.group(1).split("```")[0]
    return ""


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
    )
    code = ""
    feedback = ""
    for attempt in range(ATTEMPTS):
        prompt = base + feedback + "\nReturn only the code in one ```python block."
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if "def f" not in candidate:
            feedback = "\n\nYour reply did not define a function. Define `def f(xs):` exactly.\n"
            continue
        code = candidate
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except Exception:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        ]
        feedback = (
            "\n\nYour previous attempt was:\n```python\n" + code + "```\n"
            "It was wrong on:\n" + "\n".join(lines)
            + "\nFind the rule that matches ALL examples and rewrite f.\n"
        )
    return code or "def f(xs):\n    return []\n"
