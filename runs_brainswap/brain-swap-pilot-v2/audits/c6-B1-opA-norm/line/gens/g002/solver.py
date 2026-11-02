"""Seed solver. Every lineage starts from this exact file.

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
    "Infer the simplest general rule that explains every example. Never special-case "
    "shown inputs or hardcode outputs. Return only the code."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "First state the rule in one sentence, then verify it by hand on at least two examples.",
    "Distinguish value-based rules from position-based rules (index i versus value xs[i]), "
    "and from rules that depend on earlier elements (running or cumulative state).",
    "Consider edge cases: empty list, single element, negative values, duplicates, and "
    "whether the output length equals the input length or depends on a filter.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1]
    return text


def _base_prompt(task):
    shown = "\n".join(
        f"f({ex['input']}) == {ex['output']}" for ex in task["examples"]
    )
    hints = "".join(f"Hint: {h}\n" for h in HINTS)
    return (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n"
        + shown
        + "\n\n"
        + hints
        + "Return only the code in one ```python block."
    )


def _feedback(attempt, code, failing):
    first = failing[0]
    return (
        f"\n\nAttempt {attempt} was wrong on f({first.get('input')}): it returned "
        f"{first.get('actual')}, but the expected output is {first.get('expected')}. "
        f"{len(failing)} shown example(s) fail in total.\n"
        f"Previous code:\n```python\n{code}\n```\n"
        "Find one general rule that fits ALL examples, not a patch for this case. "
        "Return only the corrected code in one ```python block."
    )


def solve(task, api):
    prompt = _base_prompt(task)
    best_code, best_score = "", -1
    code = ""
    for attempt in range(max(1, ATTEMPTS)):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not USE_CHECK:
            return code

        try:
            results = api.check(code)
        except api.BudgetExceeded:
            return best_code or code
        except Exception:
            results = []

        passed = sum(1 for r in results if r.get("passed"))
        total = len(results)
        if total and passed == total:
            return code  # fits every shown example; keep it
        if passed > best_score:
            best_code, best_score = code, passed

        failing = [r for r in results if not r.get("passed")]
        if failing:
            prompt += _feedback(attempt + 1, code, failing)

    return best_code or code

