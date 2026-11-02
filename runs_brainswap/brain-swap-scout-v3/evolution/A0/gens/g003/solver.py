"""Seed solver, revised in generation 2.

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
    "Reply with code only."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "First look for a per-element rule (comparison with neighbours, position, running "
    "value, counts of earlier elements). Then check how the output length relates to the input.",
    "Test your candidate rule by hand against every example before answering. Pay attention "
    "to negative numbers, zeros, duplicates and empty lists.",
    "Define exactly `def f(xs):` returning a list of ints, using only the standard library.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    defs = [b for b in blocks if "def f" in b]
    if defs:
        return defs[-1]
    # Unclosed fence or bare code: take from the first `def f` onward.
    match = re.search(r"(def f\s*\(.*)", text, re.DOTALL)
    if match:
        return match.group(1).replace("```", "")
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
    best_code, best_score = "", -1
    last_code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        last_code = code
        if "def f" not in code:
            prompt = (
                base
                + "\n\nYour previous reply did not define a function named f. "
                "Reply with a ```python block containing def f(xs):."
            )
            continue
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
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
        prompt = (
            base
            + "\n\nPrevious attempt:\n```python\n" + code + "\n```\n"
            + "It failed on:\n" + "\n".join(lines)
            + "\nFind a rule that fits all examples and rewrite f. Reply with code only."
        )
    return best_code or last_code
