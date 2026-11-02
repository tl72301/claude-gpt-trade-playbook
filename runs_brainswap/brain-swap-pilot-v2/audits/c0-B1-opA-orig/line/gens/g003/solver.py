"""Solver generation 2. Verify-and-retry with robust extraction and general-rule prompting."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the general rule behind the examples, not special cases."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Look for a rule that applies to every element and every position, not one that fits only the examples.",
    "Check the output length and ordering against each example before answering.",
    "Do not return a constant or a hard-coded list unless every example requires it.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if "def f" in block:
            return block
    idx = text.find("def f")
    if idx != -1:
        return text[idx:]
    return blocks[-1] if blocks else text


def has_function(code):
    return re.search(r"def\s+f\s*\(", code) is not None


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    prompt = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below. The function must be named f.\n\n"
        + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block."
    )
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if has_function(candidate):
            code = candidate
        elif not code:
            code = candidate
        if not USE_CHECK:
            return code
        try:
            report = api.check(candidate)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return candidate
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        ]
        prompt += (
            f"\n\nAttempt {attempt + 1} was wrong on these examples:\n"
            + "\n".join(lines)
            + "\nFind the general rule that explains all examples and rewrite f. "
            "Keep the name f and return only one ```python block."
        )
    return code
