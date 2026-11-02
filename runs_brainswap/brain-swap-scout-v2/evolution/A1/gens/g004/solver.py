"""Seed solver, revised in generation 3.

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
    "Reply with only one complete Python code block that defines def f(xs)."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "The output length may differ from the input length; derive the length rule from the examples first.",
    "Common patterns: element-wise maps, running or prefix aggregates, comparisons with neighbours, "
    "sliding windows, filtering, counting, and sorting.",
    "Verify your rule by hand against every example before writing the code.",
    "Use only the Python standard library and define the function exactly as def f(xs):.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if "def f" in block:
            return block
    if blocks:
        return blocks[-1]
    idx = text.find("def f")
    if idx >= 0:
        return text[idx:]
    return text


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
            for r in failed[:3]
        ]
        prompt = (
            base
            + f"\n\nAttempt {attempt + 1} was wrong:\n"
            + "\n".join(lines)
            + "\nRe-derive the rule from all examples and return a corrected full function in one ```python block."
        )
    return code
