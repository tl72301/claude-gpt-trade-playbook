"""Solver v2: robust extraction, checked refinement loop, best-so-far retention."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the single general rule that explains ALL examples, not just a special case. "
    "Prefer simple, general logic. Always define a top-level function named f."
)
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Look for rules based on position, prefix/suffix, running counts, pairwise comparisons, "
    "neighbours, or sorting/filtering. Check the rule against every example before answering.",
    "The output length may differ from the input length; work out how it depends on the input.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if re.search(r"def\s+f\s*\(", block):
            return block
    idx = text.find("def f(")
    if idx >= 0:
        return text[idx:]
    return blocks[-1] if blocks else text


def describe_failures(report, limit=3):
    failed = [r for r in report if not r["passed"]]
    lines = []
    for r in failed[:limit]:
        lines.append(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
        )
    return failed, "\n".join(lines)


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block, with no test code."
    )
    prompt = base
    best_code, best_score = "", -1
    for attempt in range(ATTEMPTS):
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
        passed = sum(1 for r in report if r["passed"])
        if passed > best_score:
            best_code, best_score = code, passed
        failed, detail = describe_failures(report)
        if not failed and report:
            return code
        prompt = (
            base
            + f"\n\nYour previous attempt was:\n```python\n{code}```\n"
            + f"It failed on these examples:\n{detail}\n"
            + "Find the rule that fits all examples and rewrite the function. Return only the code in one ```python block."
        )
    return best_code
