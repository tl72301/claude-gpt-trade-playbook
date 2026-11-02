"""Solver: multi-attempt with check feedback, robust extraction, guaranteed def f."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Study the relation between input length and output length across all examples "
    "(e.g. pairwise/windowed ops give len-1 or len-2 outputs; sorted/prefix ops keep length).",
    "Consider: prefix sums, running max/min, adjacent differences/sums, sliding windows, "
    "filtering by predicate then transforming, sorting, counting, index-weighted values.",
    "Verify your hypothesis by hand against EVERY example before answering.",
    "Handle edge cases (empty list, short lists) without raising exceptions.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for b in reversed(blocks):
        if re.search(r"def\s+f\s*\(", b):
            return b
    if blocks:
        return blocks[-1]
    m = re.search(r"(def\s+f\s*\(.*)", text, re.DOTALL)
    return m.group(1) if m else text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    prompt = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Think briefly about the rule, then return the code in one ```python block "
        "that defines `def f(xs):` (imports inside or above it)."
    )
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        cand = extract(reply)
        if not re.search(r"def\s+f\s*\(", cand):
            prompt += "\n\nYour reply had no `def f(xs):` in a ```python block. Try again."
            continue
        code = cand
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
            f"{first['actual']}, expected {first['expected']}. "
            "Reconsider the rule from scratch and fix it."
        )
    return code
