"""Seed solver, revised. Every lineage starts from this exact file.

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
    "Reply with code only."
)
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Try the simplest rule first: per-position, running, pairwise, windowed, or filtering.",
    "Verify the output length rule (same length, shorter, or a single value) against every example.",
    "Handle empty lists and negative numbers; do not assume positivity.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    defs = [b for b in blocks if "def f" in b]
    if defs:
        return defs[-1]
    if blocks:
        return blocks[-1]
    match = re.search(r"(def f\(.*)", text, re.DOTALL)
    return match.group(1) if match else text


def feedback(report, code):
    failed = [r for r in report if not r["passed"]]
    lines = [f"Your previous attempt was:\n```python\n{code.strip()}\n```"]
    lines.append("It failed on these examples:")
    for item in failed[:3]:
        lines.append(
            f"  f({item['input']}) returned {item['actual']}, expected {item['expected']}"
        )
    lines.append("Find the rule that fits ALL examples and return a corrected full function.")
    return "\n".join(lines)


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below. Standard library only.\n\n"
        + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block that defines `def f(xs):`."
    )
    prompt = base
    best_code, best_score = "", -1
    for attempt in range(max(1, ATTEMPTS)):
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
        score = sum(1 for r in report if r["passed"])
        if score > best_score:
            best_code, best_score = code, score
        if score == len(report):
            return code
        prompt = base + "\n\n" + feedback(report, code)
    return best_code
