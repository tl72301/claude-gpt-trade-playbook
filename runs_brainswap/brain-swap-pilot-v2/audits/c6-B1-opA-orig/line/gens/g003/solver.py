"""Seed solver, revision 3. Keeps the harness contract.

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
MAX_FEEDBACK = 8
HINTS = [
    "Find one general rule that explains every example; never hardcode outputs, "
    "never special-case specific inputs, and never return a constant or a fallback "
    "that ignores xs.",
    "Name the index or value each output element is computed from, and check that the "
    "output length matches the rule (it often depends on the input length or on a filter).",
    "Handle empty lists, single elements, negative numbers and repeated values "
    "without crashing.",
    "If several rules fit, choose the simplest natural one; it is more likely to "
    "hold on unseen inputs.",
]

DEF_RE = re.compile(r"^def f\(", re.MULTILINE)
SIG_RE = re.compile(r"^def f\(\s*xs\b", re.MULTILINE)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    with_def = [block for block in blocks if DEF_RE.search(block)]
    if with_def:
        return with_def[-1]
    if blocks:
        return blocks[-1]
    match = re.search(r"^(def f\(.*)", text, re.DOTALL | re.MULTILINE)
    return match.group(1) if match else text


def is_valid(code):
    """Cheap structural checks before spending a check call."""
    if not SIG_RE.search(code):
        return False
    try:
        compile(code, "solution.py", "exec")
    except (SyntaxError, ValueError):
        return False
    return True


def _passed(report):
    return sum(1 for item in report if item.get("passed"))


def _failure_text(report):
    failed = [item for item in report if not item.get("passed")]
    return "\n".join(
        f"f({item.get('input')!r}) returned {item.get('actual')!r}, "
        f"expected {item.get('expected')!r}"
        for item in failed[:MAX_FEEDBACK]
    )


def _base_prompt(task):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    return (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        "Work in this order:\n"
        "1. State the rule in one sentence, naming the index or value each output element uses.\n"
        "2. Hand-trace the rule on two examples, one of them with negatives or duplicates.\n"
        "3. Write the function implementing that rule.\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "\nReturn the code in one ```python block that defines def f(xs)."
    )


def solve(task, api):
    base = _base_prompt(task)
    prompt = base
    best_code, best_score = None, -1
    fallback = None
    last = ""
    for _ in range(max(1, ATTEMPTS)):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        last = code
        if not is_valid(code):
            prompt = (
                base
                + "\n\nYour last reply did not contain a valid `def f(xs):` in a ```python "
                + "block that uses xs. Return only the complete corrected code."
            )
            continue
        fallback = code
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
            # Fits every shown example. Shown fit is necessary, not sufficient,
            # so return the first fully consistent rule rather than rewriting it.
            return code
        if score > best_score:
            best_code, best_score = code, score
        prompt = (
            base
            + f"\n\nPrevious attempt:\n```python\n{code}```\n"
            + f"It passed {score}/{len(report)} shown examples. Failing examples:\n"
            + _failure_text(report)
            + "\n\nThe rule behind that code is wrong for these cases. Do not patch it with "
            + "special cases. Find a different general rule that explains all examples, "
            + "then return only the corrected code in one ```python block."
        )
    return best_code or fallback or last
