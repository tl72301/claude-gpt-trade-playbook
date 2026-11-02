"""Seed solver with check-feedback repair. Every lineage starts from this exact file.

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
    "Infer the single general rule that explains every example; never hard-code the examples."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Look for one general rule (arithmetic, filtering, per-position or running computation) that fits all examples.",
    "Handle empty lists, zeros, negative numbers and length-one lists.",
    "The output must be a list of ints; return [] when nothing qualifies.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


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
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:4]
        )
        prompt = (
            base
            + "\n\nYour previous code:\n```python\n" + code + "\n```\n"
            + "It failed on:\n" + details + "\n"
            + "Find the general rule that fits ALL examples and return the full corrected "
            + "function in one ```python block."
        )
    return code
