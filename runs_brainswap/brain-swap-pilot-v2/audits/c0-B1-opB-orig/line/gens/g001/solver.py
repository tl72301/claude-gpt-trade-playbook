"""Infer a list transformation from examples and verify it against those examples."""

import re

SYSTEM = (
    "You infer precise Python list transformations from examples. "
    "Prefer simple rules that explain every example and generalize to unseen inputs."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation and write def f(xs), returning a list of ints.\n"
        "Use ALL examples as constraints. First reason about plausible simple rules, "
        "including filtering before or after mapping, positions versus values, "
        "adjacent elements, counts, ordering, duplicates, and negative numbers. "
        "Check each candidate against every example; do not assume a rule from one "
        "example alone. Prefer the simplest consistent rule, not memorized examples. "
        "Consider empty and short inputs and avoid mutating the input.\n\n"
        + shown
        + "\n\nReturn the final function in a single Python code block."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        try:
            if api.budget().get("checks", 0) <= 0:
                return code
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            "\n\nYour previous code was:\n```python\n" + code + "\n```\n"
            "It failed these examples:\n" + details
            + "\nReconsider the underlying rule using all examples, then return "
            "a corrected complete function in a Python code block."
        )
    return code
