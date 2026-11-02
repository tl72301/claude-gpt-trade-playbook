"""Seed solver, revised in generation 2.

Changes: checker feedback is used across several attempts, the best-scoring
attempt is kept if none passes, and the prompt asks for a rule that fits every
shown example.
"""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Find one rule that explains every example exactly, including empty lists and length changes.",
    "Before answering, check the rule by hand on at least two examples.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1]
    match = re.search(r"(def f\(.*)", text, re.DOTALL)
    return match.group(1) if match else text


def describe_failures(report):
    lines = []
    for r in report:
        if not r["passed"]:
            lines.append(
                f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            )
    return "\n".join(lines[:5])


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block."
    )
    best_code, best_score = "", -1
    feedback = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(base + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        except Exception as exc:
            feedback = f"\n\nAttempt {attempt + 1} crashed with {exc!r}. Write a corrected, self-contained function."
            continue
        passed = sum(1 for r in report if r["passed"])
        if passed > best_score:
            best_code, best_score = code, passed
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        feedback = (
            f"\n\nAttempt {attempt + 1} was wrong on these examples:\n"
            + describe_failures(report)
            + "\nFind a rule consistent with ALL examples and return the full corrected function."
        )
    return best_code or code if "code" in dir() else best_code
