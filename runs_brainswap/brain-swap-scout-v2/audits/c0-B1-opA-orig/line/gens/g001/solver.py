"""Seed solver, revised in generation 1.

CONTRACT (enforced by the harness)
  solve(task, api) -> str      Python source defining def f(xs) -> list[int].
  task: {"id", "examples": [{"input": [...], "output": [...]}], "signature"}
  api.llm(prompt=None, *, messages=None, system=None, max_tokens=None) -> str
  api.check(code) -> [{"passed", "input", "expected", "actual"}]   (shown examples only)
  api.budget() -> remaining {"llm_calls", "output_tokens", "checks"}
  api.BudgetExceeded is raised when the budget is spent.
  Standard library only. No file, network or process access.
"""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the general rule that explains every example, not a lookup of the examples. "
    "Check your rule by hand against each example before answering."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Look at how each output element relates to input positions, neighbours, pairs, or running values.",
    "Outputs may be shorter or longer than the input; work out the length rule first.",
    "Negative numbers, zeros, and empty lists are common edge cases.",
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
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:5]
        ]
        prompt = (
            base
            + f"\n\nA previous attempt was wrong (attempt {attempt + 1}):\n```python\n{code}\n```\n"
            + "Failures:\n" + "\n".join(lines) + "\n"
            + "Find the general rule that explains ALL examples, fix the function, "
            + "and return only the corrected code in one ```python block."
        )
    return code
