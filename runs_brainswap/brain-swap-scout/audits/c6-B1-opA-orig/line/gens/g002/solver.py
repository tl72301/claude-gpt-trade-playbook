"""Seed solver, generation 2: rule-first prompting with check-feedback repair."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 3
USE_CHECK = True
HINTS = []


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if "def f" in block:
            return block
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    prompt = (
        "Find the rule that maps each input list to its output list. First state the "
        "rule in one sentence and check it by hand against every example. Then write "
        "`def f(xs):` implementing it, returning a list of ints. Pay attention to "
        "negative numbers, empty lists, element positions, and length changes.\n\n"
        + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return the rule, then the code in one ```python block."
    )
    best_code, best_failures = "", None
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
            if best_failures is None:
                best_code = code
            break
        except Exception:
            report = None
        if not report:
            if best_failures is None:
                best_code, best_failures = code, 1
            break
        failed = [r for r in report if not r["passed"]]
        if best_failures is None or len(failed) < best_failures:
            best_code, best_failures = code, len(failed)
        if not failed:
            return code
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        ]
        prompt = (
            "Your previous attempt:\n```python\n" + code + "\n```\n"
            "It failed on these examples:\n" + "\n".join(lines) + "\n\n"
            "Re-examine the rule against all examples, then return a corrected "
            "`def f(xs):` in one ```python block.\n\nExamples:\n" + shown
        )
    return best_code
