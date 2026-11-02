"""Infer a list transformation from examples and validate the proposed code."""

import re

SYSTEM = (
    "You infer deterministic Python list transformations from examples. "
    "Prefer general rules over memorization and return standard-library Python."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']}) == {ex['output']}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation and write def f(xs), returning a list "
        "of ints. Do not hardcode examples.\n"
        "First, trace each output back to possible input values, indices, or "
        "adjacent pairs. Consider multiple competing rules and test each against "
        "EVERY example. Pay special attention to ordering, repeated values, "
        "negative values, zero, boundaries, and whether filtering happens before "
        "or after a transformation. Consider positions, neighbors, local patterns, "
        "divisibility, and simple arithmetic. For ambiguous examples, seek a rule "
        "that also explains why seemingly similar values are excluded. Prefer a "
        "simple consistent rule rather than an accidental correlation.\n\n"
        + shown
        + "\n\nReturn only executable code in a Python fenced block."
    )
    code = ""
    for _ in range(3):
        try:
            candidate = extract(api.llm(prompt, system=SYSTEM))
            code = candidate
            if api.budget().get("checks", 0) <= 0:
                break
            report = api.check(candidate)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            break
        details = "\n".join(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed
        )
        prompt += (
            "\n\nThe following candidate failed validation:\n```python\n"
            + candidate
            + "\n```\n"
            + details
            + "\nReconsider the underlying rule using all examples. Return corrected code only."
        )
    return code
