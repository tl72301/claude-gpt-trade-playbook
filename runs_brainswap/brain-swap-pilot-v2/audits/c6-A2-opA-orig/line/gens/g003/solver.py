"""Solver, revised in generation 4.

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

SYSTEM = "You write small, correct Python functions from input/output examples."
MAX_ATTEMPTS = 4
HINTS = []

FALLBACK = "def f(xs):\n    return list(xs)\n"


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if "def f" in block:
            return block
    if blocks:
        return blocks[-1]
    m = re.search(r"(def f\(.*)", text, re.DOTALL)
    return m.group(1) if m else text


def ensure_f(code):
    if not isinstance(code, str) or "def f" not in code:
        return FALLBACK
    return code


def passed_count(report):
    return sum(1 for r in report if isinstance(r, dict) and r.get("passed"))


def failure_lines(report):
    lines = []
    for r in report:
        if isinstance(r, dict) and not r.get("passed"):
            lines.append(
                f"f({r.get('input')}) returned {r.get('actual')}, expected {r.get('expected')}"
            )
    return lines


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "First, in one or two sentences, state the rule that maps input to output and "
        "check it against every example (including empty outputs and output length). "
        "Then write the code. Return only the code in one ```python block defining f."
    )
    best_code, best_score = FALLBACK, -1
    prompt = base
    for _ in range(MAX_ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        except Exception:
            break
        code = ensure_f(extract(reply))
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            if best_score < 0:
                best_code = code
            break
        except Exception:
            if best_score < 0:
                best_code = code
            break
        if not isinstance(report, list) or not report:
            if best_score < 0:
                best_code, best_score = code, 0
            break
        score = passed_count(report)
        if score > best_score:
            best_code, best_score = code, score
        failed = failure_lines(report)
        if not failed:
            break
        prompt = (
            base
            + "\n\nPrevious attempt:\n```python\n" + code + "```\n"
            + "It failed on these examples:\n- " + "\n- ".join(failed[:6])
            + "\nThe rule must fit ALL examples, not just the failing ones. "
            "Revise the rule, then rewrite f in one ```python block."
        )
    return best_code
