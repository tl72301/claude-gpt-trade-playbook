"""Solver, revised in generation 4.

CONTRACT (enforced by the harness)
  solve(task, api) -> str      Python source defining def f(xs) -> list[int].
"""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the exact rule for every output position before writing code."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "The output length is often different from the input length (filters, windows, "
    "pairwise operations, counts). Verify the length rule on every example.",
    "State the rule in one sentence, check it by hand on one example, then code it.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def ensure_f(code):
    # Models often name the function differently; alias the last def to f.
    if re.search(r"def\s+f\s*\(", code):
        return code
    names = re.findall(r"def\s+(\w+)\s*\(", code)
    if names:
        return code + f"\n\nf = {names[-1]}\n"
    return code


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block."
    )
    prompt = base
    best_code, best_fails = "", None
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = ensure_f(extract(reply))
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if best_fails is None or len(failed) < best_fails:
            best_code, best_fails = code, len(failed)
        if not failed:
            return code
        first = failed[0]
        actual = first["actual"]
        expected = first["expected"]
        note = ""
        if isinstance(actual, list) and isinstance(expected, list) and len(actual) != len(expected):
            note = (f" Your output length was {len(actual)} but should be {len(expected)}; "
                    "fix the length rule first.")
        prompt = (
            base
            + f"\n\nPrevious attempt:\n```python\n{code}\n```\n"
            + f"It was wrong: f({first['input']}) returned {actual}, expected {expected}.{note} "
            + "Re-derive the rule from all examples and return a corrected ```python block."
        )
    return best_code or ensure_f(extract(""))
