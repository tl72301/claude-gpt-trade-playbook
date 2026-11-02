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
    "The function must be named f and take a single list argument xs."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Verify the rule against every example before answering.",
    "Outputs often depend on position, length, prefix/suffix, neighbouring elements, "
    "running counts or running extremes, differences between neighbours, or sliding windows.",
    "The output length may differ from the input length; derive it from the rule.",
    "Do not print anything and do not read input; just define f.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if not blocks:
        blocks = [text]
    for block in reversed(blocks):
        if re.search(r"def\s+f\s*\(", block):
            return block
    return blocks[-1]


def describe_failures(report):
    failed = [r for r in report if not r["passed"]]
    lines = []
    for r in failed[:4]:
        lines.append(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
        )
    return "\n".join(lines)


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below. Use only the standard library.\n\n"
        + shown + "\n\n"
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
        if all(r["passed"] for r in report):
            return code
        prompt = (
            base
            + "\n\nA previous attempt was:\n```python\n" + code + "```\n"
            + "It was wrong on these examples:\n" + describe_failures(report)
            + "\n\nFind the rule that fits all examples and return corrected code "
            + "defining f, in one ```python block."
        )
    return code
