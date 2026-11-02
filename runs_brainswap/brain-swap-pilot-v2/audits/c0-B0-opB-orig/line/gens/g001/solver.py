"""Infer a list transformation from examples and validate the proposed code."""

import re

SYSTEM = (
    "You infer simple deterministic Python list transformations from examples. "
    "Prefer general rules over memorization. Return executable standard-library Python."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']}) == {ex['output']}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation and write def f(xs), returning a list of ints.\n"
        "Consider multiple plausible rules before choosing. Check the rule against EVERY "
        "example, including output order, duplicates, empty results, negative numbers, "
        "indices versus values, filtering before versus after transformation, and "
        "boundary cases. Do not hardcode examples. Prefer the simplest rule that explains "
        "all examples. In particular, consider adjacent pairs, positions, divisibility, "
        "and arithmetic transformations when appropriate.\n\n"
        + shown
        + "\n\nReturn only the final code in a Python fenced block."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
            candidate = extract(reply)
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
            + "\nReconsider the underlying rule using all examples, not just this failure. "
            "Return corrected code only."
        )
    return code
