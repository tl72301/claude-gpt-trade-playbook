"""Seed solver, revised. Keeps the harness contract.

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
    "You infer the general rule behind the examples, not a lookup of them."
)
ATTEMPTS = 3
USE_CHECK = True
MAX_FEEDBACK = 6
HINTS = [
    "Find one general rule that explains every example; never hardcode outputs "
    "or special-case specific inputs.",
    "Before answering, trace your rule by hand on at least two examples, checking "
    "which index or which value each output element is computed from.",
    "Handle empty lists, single elements, negative numbers and repeated values "
    "without crashing.",
    "If several rules fit, choose the simplest natural one; it is more likely to "
    "hold on unseen inputs.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1]
    match = re.search(r"(def f\(.*)", text, re.DOTALL)
    return match.group(1) if match else text


def _passed(report):
    return sum(1 for item in report if item.get("passed"))


def _failure_text(report):
    failed = [item for item in report if not item.get("passed")]
    lines = [
        f"f({item.get('input')!r}) returned {item.get('actual')!r}, "
        f"expected {item.get('expected')!r}"
        for item in failed[:MAX_FEEDBACK]
    ]
    return "\n".join(lines)


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
    for _ in range(max(1, ATTEMPTS)):
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
        if not report:
            return code
        score = _passed(report)
        if score == len(report):
            # Fits every shown example; keep it rather than risk a worse rewrite.
            return code
        if score > best_score:
            best_code, best_score = code, score
        prompt = (
            base
            + f"\n\nPrevious attempt:\n```python\n{code}```\n"
            + f"It passed {score}/{len(report)} shown examples. Failing examples:\n"
            + _failure_text(report)
            + "\nFind the general rule that fits all examples, including these. "
            + "Return only the corrected code in one ```python block."
        )
    return best_code or code
