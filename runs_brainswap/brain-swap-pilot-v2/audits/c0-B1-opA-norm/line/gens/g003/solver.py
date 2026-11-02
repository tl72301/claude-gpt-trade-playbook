"""Solver with check-driven repair loop. Keeps the seed contract."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 5
USE_CHECK = True
SHOW = 5
HINTS = [
    "Find the simplest single rule that fits every example, including edge cases "
    "such as empty lists, zeros and negative numbers.",
    "Compare the output length, order and values with each example before answering.",
    "The output may depend on neighbouring elements, running totals, pairwise "
    "differences or filtering by sign; test each candidate rule against all examples.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        good = [b for b in blocks if "def f" in b]
        return good[-1] if good else blocks[-1]
    start = text.find("def f")
    return text[start:] if start >= 0 else text


def solve(task, api):
    examples = "\n".join(
        f"f({e['input']}) == {e['output']}" for e in task["examples"]
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
    best_code, best_score = "", -1
    last = ""
    for _ in range(ATTEMPTS):
        try:
            reply = api.llm(base + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        last = code
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
        score = sum(1 for r in results if r.get("passed"))
        if score > best_score:
            best_code, best_score = code, score
        failed = [r for r in results if not r.get("passed")][:SHOW]
        if not failed:
            continue
        lines = "\n".join(
            f"- f({r.get('input')}) returned {r.get('actual')}, expected {r.get('expected')}"
            for r in failed
        )
        feedback = (
            "\n\nYour previous attempt was:\n```python\n" + code + "\n```\n"
            "It failed these examples:\n" + lines + "\n"
            "Find the single rule that fits all examples, fix the bug, and return a "
            "corrected complete ```python block."
        )
    return best_code or last

