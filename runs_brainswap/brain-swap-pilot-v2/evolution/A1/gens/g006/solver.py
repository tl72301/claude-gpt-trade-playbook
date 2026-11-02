"""Seed solver, revised in generation 3.

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
    "You always name the function exactly f and reply with one ```python block. "
    "Before coding, state the rule that maps each input to its output, and check it "
    "against every example, including the lengths of the outputs."
)
ATTEMPTS = 3
HINTS = [
    "The function must be named exactly f and take one argument xs.",
    "Inputs may contain negative numbers and zeros; do not assume they are positive.",
    "Output length may differ from input length. Infer the rule from every example before coding.",
    "Each output element may depend on a window, a prefix, or a comparison with neighbours; "
    "test your rule by hand on at least two examples before answering.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    if not blocks:
        m = re.search(r"```(?:python|py)?[ \t]*\n(.*)", text, re.DOTALL)
        blocks = [m.group(1)] if m else [text]
    for block in reversed(blocks):
        if "def " in block:
            return block
    return blocks[-1]


def ensure_f(code):
    """Make sure the code defines f. If only a misnamed def exists, alias the last one to f."""
    if re.search(r"^def f\s*\(", code, re.MULTILINE):
        return code
    names = re.findall(r"^def\s+(\w+)\s*\(", code, re.MULTILINE)
    if names:
        return code + f"\n\nf = {names[-1]}\n"
    return code


def base_prompt(task):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    return (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block."
    )


def feedback(report):
    if not report:
        return "Your code did not define a usable function f. Define def f(xs) and return a list."
    failed = [r for r in report if not r.get("passed")]
    if not failed:
        return ""
    lines = []
    for item in failed[:4]:
        lines.append(
            f"f({item.get('input')}) returned {item.get('actual')}, expected {item.get('expected')}"
        )
    return (
        "Some examples failed:\n" + "\n".join(lines)
        + "\nThe rule is wrong, not just the code. Re-derive it from the examples, "
        "check the output length first, then fix it."
    )


def solve(task, api):
    base = base_prompt(task)
    best_code, best_score = "", -1
    extra = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(base + extra, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = ensure_f(extract(reply))
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return best_code or code
        except Exception:
            report = []
        total = len(report) if report else 0
        passed = sum(1 for r in report if r.get("passed")) if report else 0
        if total and passed == total:
            return code
        if passed > best_score:
            best_code, best_score = code, passed
        extra = (
            f"\n\nAttempt {attempt + 1} was wrong.\n"
            + feedback(report)
            + "\nPrevious code:\n```python\n" + code + "```\n"
        )
    return best_code or "def f(xs):\n    return list(xs)\n"
