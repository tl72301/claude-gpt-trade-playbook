"""Solver v2: generate, check against shown examples, repair with feedback, keep best."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Reply with code only."
)
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Empty outputs are possible; handle cases where no element qualifies.",
    "Look for a per-element, per-adjacent-pair, or running-state rule.",
    "The function must be named exactly f and take one argument xs.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        for block in reversed(blocks):
            if "def f" in block:
                return block
        return blocks[-1]
    return text


def failure_text(failed):
    lines = []
    for item in failed[:3]:
        lines.append(
            f"f({item['input']}) returned {item.get('actual')}, "
            f"expected {item.get('expected')}"
        )
    return "\n".join(lines)


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
    best_code, best_failed = "", None
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if "def f" not in code:
            prompt = base + (
                "\n\nYour last reply did not define a function named f. "
                "Reply with a ```python block containing `def f(xs):`."
            )
            continue
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        if best_failed is None or len(failed) < len(best_failed):
            best_code, best_failed = code, failed
        prompt = (
            base
            + "\n\nYour previous attempt was wrong:\n"
            + failure_text(failed)
            + "\nThe previous code was:\n```python\n"
            + code
            + "\n```\nFind the rule that fits all examples and reply with a corrected "
            "version in one ```python block."
        )
    return best_code or code
