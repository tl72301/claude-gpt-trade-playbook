"""Solver v2: verify against shown examples, retry with concrete feedback, keep the best candidate."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "You infer the general rule behind the examples, not special cases, and you "
    "always define the function with the exact name and signature requested."
)
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Define exactly `def f(xs):` at top level. Use only the standard library.",
    "Do not read input or print anything. Return a new list of ints.",
    "Handle empty lists and negative numbers. Check the rule against every example before answering.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    with_f = [b for b in blocks if has_f(b)]
    if with_f:
        return with_f[-1]
    if blocks:
        return blocks[-1]
    return text


def has_f(code):
    return re.search(r"^\s*def\s+f\s*\(", code, re.MULTILINE) is not None


def describe_failures(report, limit=4):
    lines = []
    for r in report:
        if r.get("passed"):
            continue
        lines.append(
            f"f({r.get('input')}) returned {r.get('actual')}, expected {r.get('expected')}"
        )
        if len(lines) >= limit:
            break
    return "\n".join(lines)


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints.\n"
        "It must be consistent with every example below and must implement the general "
        "rule that produces them.\n\n"
        + shown + "\n\n"
        + "".join(f"{hint}\n" for hint in HINTS)
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
        if not has_f(code):
            prompt = base + "\n\nYour previous answer did not define `def f(xs):`. Define it exactly."
            continue
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        except Exception:
            report = []
        if not report:
            return code
        score = sum(1 for r in report if r.get("passed"))
        if score > best_score:
            best_code, best_score = code, score
        failed = [r for r in report if not r.get("passed")]
        if not failed:
            return code
        prompt = (
            base
            + "\n\nYour previous attempt was wrong on these examples:\n"
            + describe_failures(report)
            + "\nRevise the rule so it fits all examples, not just some. Return the full code again."
        )
    return best_code or last_code or "def f(xs):\n    return list(xs)\n"

