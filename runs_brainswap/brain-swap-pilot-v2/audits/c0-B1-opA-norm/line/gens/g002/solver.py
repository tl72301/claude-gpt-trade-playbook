"""Solver with check-driven repair loop. Keeps the seed contract."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Find the simplest single rule that fits every example, including edge cases "
    "such as empty lists, zeros and negative numbers.",
    "Check the output length and order against each example before answering.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        with_def = [b for b in blocks if "def f" in b]
        return with_def[-1] if with_def else blocks[-1]
    i = text.find("def f")
    return text[i:] if i >= 0 else text


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']}) == {ex['output']}" for ex in task["examples"]
    )
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n"
        + examples
        + "\n\n"
        + "".join(f"Hint: {h}\n" for h in HINTS)
        + "Return only the complete code in one ```python block."
    )
    feedback = ""
    code = ""
    best_code, best_score = "", -1
    for _ in range(ATTEMPTS):
        try:
            raw = api.llm(base + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(raw)
        if not USE_CHECK:
            return code
        try:
            results = api.check(code)
        except api.BudgetExceeded:
            break
        except Exception:
            results = []
        if results and all(r.get("passed") for r in results):
            return code
        passed = sum(1 for r in results if r.get("passed"))
        if passed > best_score:
            best_code, best_score = code, passed
        failing = [r for r in results if not r.get("passed")][:3]
        if not failing:
            continue
        lines = "\n".join(
            f"- f({r.get('input')}) returned {r.get('actual')}, expected {r.get('expected')}"
            for r in failing
        )
        feedback = (
            "\n\nYour previous attempt failed these examples:\n"
            + lines
            + "\nRe-derive the rule from all examples and return a corrected complete "
            "```python block."
        )
    return best_code or code
