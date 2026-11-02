"""Seed solver, generation 2: rule-first prompting with check-driven revision.

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
    "Find the simplest general rule that fits every example, since hidden tests "
    "use other inputs of the same kind."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = []


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def describe_failures(report, limit=4):
    lines = []
    for r in report:
        if r.get("passed"):
            continue
        lines.append(
            f"  f({r.get('input')}) returned {r.get('actual')}, expected {r.get('expected')}"
        )
        if len(lines) >= limit:
            break
    return "\n".join(lines)


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    prompt = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "First state the rule in one or two plain sentences and check it against each "
        "example by hand. Then give the code in one ```python block that defines def f(xs)."
    )
    best_code, best_score = "", -1
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if "def f" not in code:
            prompt += "\n\nYour code did not define def f(xs). Return a complete definition."
            continue
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        except Exception:
            return code
        passed = sum(1 for r in report if r.get("passed"))
        if passed > best_score:
            best_code, best_score = code, passed
        failed = [r for r in report if not r.get("passed")]
        if not failed:
            return code
        prompt = (
            prompt.split("\n\nPrevious attempt")[0]
            + "\n\nPrevious attempt failed these examples:\n"
            + describe_failures(report)
            + "\nFind the rule that explains ALL examples, not a patch for these. "
            "Reconsider the rule in words, then return the full corrected code in one ```python block."
        )
    return best_code or code if "code" in dir() else best_code
