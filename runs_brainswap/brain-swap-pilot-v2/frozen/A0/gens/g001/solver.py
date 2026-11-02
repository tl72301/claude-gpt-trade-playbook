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
    "Infer the exact rule from all examples before writing code. Output only code."
)
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "The rule may depend on position, neighbours, prefix or suffix, running state, or counts.",
    "Output length may differ from input length; check it against every example.",
    "Handle empty lists and negative numbers.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if re.search(r"def\s+f\s*\(", block):
            return block
    if blocks:
        return blocks[-1]
    match = re.search(r"(def\s+f\s*\(.*)", text, re.DOTALL)
    return match.group(1) if match else text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block."
    )
    history = ""
    code = ""
    best_code, best_score = "", -1
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(base + history, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not re.search(r"def\s+f\s*\(", code):
            history += (
                "\n\nYour last reply did not define `def f(xs):`. Reply with one "
                "complete ```python block that defines f(xs)."
            )
            continue
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        except Exception:
            return code
        failed = [r for r in report if not r["passed"]]
        score = len(report) - len(failed)
        if score > best_score:
            best_code, best_score = code, score
        if not failed:
            return code
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        ]
        history += (
            f"\n\nAttempt {attempt + 1} was wrong on {len(failed)} example(s):\n"
            + "\n".join(lines)
            + "\nThe code you wrote was:\n```python\n" + code + "\n```\n"
            + "Find the rule that fits ALL examples and return the full corrected code "
            "in one ```python block."
        )
    return best_code or code
