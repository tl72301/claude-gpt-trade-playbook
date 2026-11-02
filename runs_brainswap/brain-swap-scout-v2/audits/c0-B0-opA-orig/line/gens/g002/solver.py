"""Seed solver, revised in generation 2.

CONTRACT (enforced by the harness)
  solve(task, api) -> str      Python source defining def f(xs) -> list[int].
  task: {"id", "examples": [{"input": [...], "output": [...]}], "signature"}
  api.llm(prompt=None, *, messages=None, system=None, max_tokens=None) -> str
  api.check(code) -> [{"passed", "input", "expected", "actual"}]   (shown examples only)
  api.budget() -> remaining {"llm_calls", "output_tokens", "checks"}
  api.BudgetExceeded is raised when the budget is spent.
  Standard library only (see brainswap/policy.py). No file, network or process access.
"""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Find ONE simple rule that reproduces every example exactly, including output "
    "length, output order, empty results, and negative numbers. The rule must work "
    "on new inputs too, so never hardcode example values."
)
ATTEMPTS = 4
USE_CHECK = True
MAX_DETAILS = 5
HINTS = [
    "Length: decide whether the output length equals the input length, or is a filter, "
    "a count, or a pairing of neighbours (adjacent pairs give n-1 items).",
    "Order: decide whether the output keeps input order, is reversed, or is sorted.",
    "Empty results: [] is a valid answer when nothing qualifies; do not return a constant.",
    "Values: check arithmetic on negatives (floor division, modulo sign, abs) carefully.",
    "Prefer the simplest rule that fits all examples; test it by hand on every example before answering.",
]
DEF_RE = re.compile(r"def\s+f\s*\(")


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    with_def = [b for b in blocks if DEF_RE.search(b)]
    if with_def:
        return with_def[-1]
    match = DEF_RE.search(text)
    if match:
        return text[match.start():]
    return blocks[-1] if blocks else text


def has_def(code):
    return DEF_RE.search(code) is not None


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the complete code in one ```python block, defining def f(xs)."
    )
    prompt = base
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not has_def(code):
            prompt = (
                base
                + "\n\nYour last reply did not define `def f(xs):`. "
                + "Return the complete function named f in one ```python block."
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
        details = "\n".join(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:MAX_DETAILS]
        )
        prompt = (
            base
            + f"\n\nPrevious attempt (wrong):\n```python\n{code}\n```\n"
            + f"It failed on:\n{details}\n"
            + "First state which property is wrong (length, order, or values), then "
            + "find the simplest rule that fits all examples and return corrected code "
            + "in one ```python block defining def f(xs)."
        )
    return code

