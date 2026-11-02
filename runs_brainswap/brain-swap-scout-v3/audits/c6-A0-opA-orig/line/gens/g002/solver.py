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
    "Infer the exact rule from every example before writing code."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Handle empty lists, zeros, negatives and duplicates; the output may be [].",
    "Output length and order must match the examples exactly.",
]


def extract(text):
    """Return the code defining f, tolerating missing fences or stray prose."""
    blocks = re.findall(r"```[ \t]*(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    blocks = [b for b in blocks if "def f" in b]
    if blocks:
        return blocks[-1]
    match = re.search(r"^[ \t]*def f\b", text, re.MULTILINE)
    if match:
        return text[match.start():].split("```")[0]
    return text


def passed_count(report):
    return sum(1 for r in report if r["passed"])


def feedback(report):
    failed = [r for r in report if not r["passed"]]
    lines = []
    for r in failed[:3]:
        lines.append(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}."
        )
    return " ".join(lines)


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
    best_code, best_score = "", -1
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        if not report or passed_count(report) == len(report):
            return code
        score = passed_count(report)
        if score > best_score:
            best_code, best_score = code, score
        prompt = (
            base
            + f"\n\nPrevious attempt:\n```python\n{code}```\n"
            + f"It was wrong: {feedback(report)} Fix the rule so all examples match."
        )
    return best_code or code
