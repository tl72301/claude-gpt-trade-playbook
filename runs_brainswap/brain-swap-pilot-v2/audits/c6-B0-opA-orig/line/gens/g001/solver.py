"""Seed solver, improved for generalization. Keeps the harness contract."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the single most general rule that explains every example, then implement exactly that rule. "
    "Standard library only."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "First state, in one sentence, how each output element relates to the input (position, value, neighbours, running state, filtering, counting, or sorting).",
    "Output length may differ from input length. Work out what controls the length before writing code.",
    "Handle edge cases: empty list, single element, negative numbers, duplicates, and all-equal values. The rule must hold on unseen inputs.",
    "Do not hardcode example outputs, use lookup tables, or special-case particular examples.",
]
MAX_FEEDBACK = 4


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def _passed(report):
    return sum(1 for r in report if r.get("passed"))


def _failure_lines(report):
    failed = [r for r in report if not r.get("passed")]
    return "\n".join(
        f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
        for r in failed[:MAX_FEEDBACK]
    )


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block."
    )
    best_code, best_score = "", -1
    history = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(base + history, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            if best_score < 0:
                best_code = code
            break
        except Exception:
            report = []
            score = 0
        else:
            if not report:
                return code
            score = _passed(report)
            if score == len(report):
                return code
        if score > best_score:
            best_code, best_score = code, score
        if report:
            history = (
                f"\n\nPrevious attempt (passed {score}/{len(report)} examples):\n"
                f"```python\n{code}\n```\n"
                f"Failing cases:\n{_failure_lines(report)}\n"
                "Do not patch these cases one by one. Find the underlying rule that fits all examples "
                "and rewrite the function from that rule."
            )
    return best_code
