"""Solver v2: infer a rule from examples, verify against shown examples, retry with concrete mismatches.

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
    "You infer exact rules for small list-to-list functions from input/output "
    "examples. You verify your rule against every example before answering, and "
    "you pay close attention to output length, ordering, empty results, negative "
    "numbers, and index-based behavior."
)

ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "First state the rule in one sentence, then test it by hand on at least two examples.",
    "Output length may differ from input length; determine exactly what controls it.",
    "An empty list [] is a valid output when no element qualifies; do not default to it.",
    "If outputs are indices, check whether they are 0-based or 1-based and which element they refer to.",
    "Do not special-case specific examples; the rule must generalize.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1]
    idx = text.find("def f")
    return text[idx:] if idx >= 0 else text


def build_prompt(task):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    hints = "".join(f"Hint: {hint}\n" for hint in HINTS)
    return (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n"
        + shown
        + "\n\n"
        + hints
        + "Return only the final code in one ```python block, with no test code."
    )


def solve(task, api):
    base = build_prompt(task)
    feedback = ""
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(base + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        lines = "\n".join(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:5]
        )
        feedback = (
            "\n\nYour previous attempt was wrong on these examples:\n"
            + lines
            + "\nRe-derive the rule so it fits all examples, then return corrected "
            "code in one ```python block."
        )
    return code
