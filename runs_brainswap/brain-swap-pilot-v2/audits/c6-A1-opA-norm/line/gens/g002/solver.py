"""Solver, revised in generation 4.

Contract: solve(task, api) -> str, source defining def f(xs) -> list[int].
Uses api.check feedback on shown examples, renames a misnamed def to f,
and keeps the attempt that passes the most shown examples.
"""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Work out the exact rule for every output element and for the output length "
    "before writing code. The output length may differ from the input length.",
    "Check your rule by hand against every example, including empty and negative values.",
]


def extract(text):
    v0 = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return v0[-1] if v0 else text


def ensure_f(code):
    # If the model named its function differently, rename the first def to f.
    if re.search(r"^def f\s*\(", code, re.M):
        return code
    m = re.search(r"^def (\w+)\s*\(", code, re.M)
    if m:
        code = re.sub(
            r"^def %s\s*\(" % re.escape(m.group(1)), "def f(", code, count=1, flags=re.M
        )
    return code


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
        + "Return only the code in one ```python block."
    )
    prompt = base
    best_code, best_score = "", -1
    for _ in range(ATTEMPTS):
        try:
            text = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = ensure_f(extract(text))
        if not USE_CHECK:
            return code
        try:
            results = api.check(code)
        except api.BudgetExceeded:
            break
        passed = sum(1 for r in results if r.get("passed"))
        if passed > best_score:
            best_code, best_score = code, passed
        fails = [r for r in results if not r.get("passed")]
        if not fails:
            return code
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in fails[:3]
        ]
        prompt = (
            base
            + "\n\nYour previous attempt was:\n```python\n"
            + code
            + "\n```\nIt failed these examples:\n"
            + "\n".join(lines)
            + "\nFind the rule that fits ALL examples (check the output length too) "
            "and return a corrected full function in one ```python block."
        )
    return best_code


