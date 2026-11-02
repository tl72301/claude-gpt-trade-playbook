"""Solver v3: hypothesis-first generation, self-check on shown examples, repair loop."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Before coding, state a one-sentence hypothesis for the rule and test it against every example, "
    "paying attention to output length and to which input positions contribute.",
    "Typical rules: filtering by a condition, sliding windows, pairwise differences or sums, "
    "prefix sums, counting, sorting, index-based rules.",
]
FALLBACK = "def f(xs):\n    return list(xs)\n"


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if "def f" in block:
            return block
    if "def f" in text:
        return text[text.index("def f"):]
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Reply with a short rule description, then the code in one ```python block."
    )
    prompt = base
    best_code, best_score = "", -1
    for _ in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if "def f" not in code:
            prompt = base + "\n\nYour last reply had no `def f(xs)`. Return a ```python block defining def f(xs)."
            continue
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        score = len(report) - len(failed)
        if best_code == "" or score > best_score:
            best_code, best_score = code, score
        if not failed:
            return code
        feedback = "\n".join(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}" for r in failed[:3]
        )
        prompt = (
            base
            + f"\n\nPrevious attempt:\n```python\n{code}```\nIt failed:\n{feedback}\n"
            "Revise the rule so every example holds (check lengths and positions), then return the full code."
        )
    return best_code or FALLBACK
