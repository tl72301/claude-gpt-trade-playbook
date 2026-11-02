"""Seed solver, revised in generation 1.

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
    "You always name the function exactly f and reply with one ```python block."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "The function must be named exactly f and take one argument xs.",
    "Inputs may contain negative numbers and zeros; do not assume they are positive.",
    "Output length may differ from input length. Infer the rule from every example before coding.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if "def f" in block:
            return block
    if blocks:
        return blocks[-1]
    return text


def base_prompt(task):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    return (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block."
    )


def feedback(report):
    if not report:
        return "Your code did not define a usable function f. Define def f(xs) and return a list."
    failed = [r for r in report if not r["passed"]]
    if not failed:
        return ""
    lines = []
    for item in failed[:3]:
        lines.append(
            f"f({item['input']}) returned {item['actual']}, expected {item['expected']}"
        )
    return "Some examples failed:\n" + "\n".join(lines) + "\nRe-derive the rule and fix it."


def solve(task, api):
    base = base_prompt(task)
    code = ""
    extra = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(base + extra, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        except Exception:
            report = []
        if report and all(r["passed"] for r in report):
            return code
        extra = (
            f"\n\nAttempt {attempt + 1} was wrong.\n"
            + feedback(report)
            + "\nPrevious code:\n```python\n" + code + "```\n"
        )
    return code
