"""Solver, revised in generation 5.

CONTRACT (enforced by the harness)
  solve(task, api) -> str      Python source defining def f(xs) -> list[int].
"""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the exact rule for every output position before writing code."
)
ATTEMPTS = 4
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


def length_note(failed):
    # Report every length mismatch (up to 3), not just the first failure.
    notes = []
    for item in failed:
        actual, expected = item["actual"], item["expected"]
        if isinstance(actual, list) and isinstance(expected, list) and len(actual) != len(expected):
            notes.append(f"f({item['input']}) gave length {len(actual)}, expected {len(expected)}")
    if not notes:
        return ""
    return " Length errors: " + "; ".join(notes[:3]) + ". Fix the length rule first."


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
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        ]
        prompt = (
            base
            + f"\n\nPrevious attempt:\n```python\n{code}\n```\n"
            + "It was wrong on:\n" + "\n".join(lines) + "."
            + length_note(failed)
            + " Re-derive the rule from all examples, check it by hand on each one, "
            + "and return a corrected ```python block."
        )
    return best_code or ensure_f(extract(""))
