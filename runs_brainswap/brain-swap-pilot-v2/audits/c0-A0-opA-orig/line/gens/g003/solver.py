"""Seed solver, generation 3: checked repair loop with grouped failure feedback."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the general rule that explains every example, not special cases."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Try simple rule families first: filter by a predicate, map each element by its index, "
    "pairwise differences or sums, running totals, sorting, or counting.",
    "Before answering, verify the rule by hand on at least two examples, including the empty-list case.",
]
MAX_FEEDBACK = 5


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def build_prompt(task):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    return (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block."
    )


def feedback(failed):
    lines = []
    for item in failed[:MAX_FEEDBACK]:
        lines.append(
            f"f({item.get('input')}) returned {item.get('actual')}, "
            f"expected {item.get('expected')}"
        )
    more = len(failed) - MAX_FEEDBACK
    if more > 0:
        lines.append(f"...and {more} more mismatches")
    return "\n".join(lines)


def solve(task, api):
    prompt = build_prompt(task)
    best_code, best_fails = None, None
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
        if best_fails is None or len(failed) < best_fails:
            best_code, best_fails = code, len(failed)
        prompt = (
            build_prompt(task)
            + f"\n\nAttempt {attempt + 1} was wrong on {len(failed)} example(s):\n"
            + feedback(failed)
            + f"\n\nPrevious code:\n```python\n{code}\n```\n"
            + "Find the rule that fits ALL examples and return corrected code in one ```python block."
        )
    return best_code if best_code is not None else code
