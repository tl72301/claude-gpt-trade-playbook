"""Infer a list transformation from examples and validate the implementation."""

import re

SYSTEM = (
    "You infer the intended Python list transformation from input/output examples. "
    "Prefer a simple, general rule over memorizing examples. Pay close attention "
    "to ordering, multiplicity, indexing, adjacent elements, runs, and boundaries."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation and implement def f(xs), returning a "
        "list of ints. All examples must match exactly, including order and "
        "duplicates.\n\n"
        + shown
        + "\n\nFirst reason about plausible rules and test them against every "
        "example. Consider element filters, indices, adjacent pairs or windows, "
        "differences, parity, signs, and runs when appropriate. Choose the simplest "
        "consistent rule, not a lookup table. Handle empty and short inputs and "
        "boundary cases naturally. Return your final implementation in one "
        "```python code block."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if candidate:
            code = candidate
        try:
            if api.budget().get("checks", 0) <= 0:
                return code
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        prompt += (
            "\n\nThe following implementation failed the examples:\n```python\n"
            + code
            + "\n```\nFailures:\n"
            + "\n".join(
                f"f({r['input']!r}) returned {r['actual']!r}; "
                f"expected {r['expected']!r}" for r in failed
            )
            + "\nReconsider the rule and return corrected code in a Python block."
        )
    return code
