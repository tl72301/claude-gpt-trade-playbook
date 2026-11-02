"""Solver, revised in generation 6.

CONTRACT (enforced by the harness)
  solve(task, api) -> str      Python source defining def f(xs) -> list[int].
"""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the exact rule for every output position before writing code."
)
ATTEMPTS = 5
USE_CHECK = True
HINTS = [
    "Before coding, write two or three candidate rules in one line each, and test every "
    "candidate against every example. Keep only a rule that fits all examples.",
    "The output length is often different from the input length (filters, windows, "
    "pairwise operations, counts). Verify the length rule on every example.",
    "Return one ```python block that defines `def f(xs):` at top level.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1]
    return text


def has_def(code):
    return re.search(r"def\s+\w+\s*\(", code) is not None


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
    best_code, best_key = "", None
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
        # Prefer candidates that define a function at all, then fewer failures.
        key = (0 if has_def(code) else 1, len(failed))
        if best_key is None or key < best_key:
            best_code, best_key = code, key
        if not failed and has_def(code):
            return code
        if not has_def(code):
            feedback = (
                "Your reply had no `def f(xs):` at top level. "
                "Return the complete code in one ```python block."
            )
        else:
            lines = [
                f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
                for r in failed[:3]
            ]
            feedback = "It was wrong on:\n" + "\n".join(lines) + "." + length_note(failed)
        prompt = (
            base
            + f"\n\nPrevious attempt:\n```python\n{code}\n```\n"
            + feedback
            + " Re-derive the rule from all examples, check it by hand on each one, "
            + "and return a corrected ```python block."
        )
    return best_code or "def f(xs):\n    return list(xs)\n"
