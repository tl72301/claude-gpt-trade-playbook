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
    "Find the single general rule that explains every example, and consider edge cases "
    "such as empty lists, zeros, negative numbers and repeated values."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Compare input and output lengths and positions before guessing the rule.",
    "Before answering, verify your rule by hand against every example.",
    "Return a list of ints; do not print anything and do not read input.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if "def f" in block:
            return block
    if "def f" in text:
        return text[text.index("def f"):]
    return blocks[-1] if blocks else text


def describe_failures(failed):
    lines = []
    for item in failed[:3]:
        lines.append(
            f"f({item['input']}) returned {item['actual']}, expected {item['expected']}"
        )
    return "; ".join(lines)


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
        prompt = (
            base
            + f"\n\nAttempt {attempt + 1} was wrong: {describe_failures(failed)}.\n"
            + "Previous code:\n```python\n" + code + "```\n"
            + "Find the rule that explains all examples, then return a corrected "
            + "`def f(xs):` in one ```python block."
        )
    return code
