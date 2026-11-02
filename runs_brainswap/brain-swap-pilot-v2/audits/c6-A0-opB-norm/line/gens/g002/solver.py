"""Infer a list transformation from examples and validate the proposed code."""

import re

SYSTEM = (
    "You infer simple deterministic Python list transformations from examples. "
    "Prefer the simplest rule that explains all examples, including their order, "
    "and implement that rule exactly."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({example['input']!r}) == {example['output']!r}"
        for example in task["examples"]
    )
    prompt = (
        "Infer the intended general rule for def f(xs), mapping a list of integers "
        "to a list of integers.\n\n"
        + examples
        + "\n\nBefore coding, compare plausible rules against EVERY example. "
        "Pay particular attention to output order, repeated values, positions, "
        "adjacent pairs, filtering before versus after transformation, and Python "
        "modulo behavior for negative numbers. Outputs may be indices, counts, "
        "remainders, or results for adjacent elements rather than input values. "
        "Do not assume sorting or deduplication unless examples support it. "
        "Prefer a simple consistent rule over memorizing examples. Handle empty "
        "and short lists naturally. Return only the function code in a Python block."
    )
    code = ""
    for attempt in range(3):
        try:
            code = extract(api.llm(prompt, system=SYSTEM))
        except api.BudgetExceeded:
            break
        try:
            failures = [result for result in api.check(code) if not result["passed"]]
        except api.BudgetExceeded:
            break
        if not failures:
            return code
        feedback = "\n".join(
            f"f({r['input']!r}): got {r['actual']!r}, expected {r['expected']!r}"
            for r in failures
        )
        prompt += (
            "\n\nThe following implementation failed the shown examples:\n```python\n"
            + code
            + "\n```\n"
            + feedback
            + "\nReconsider the rule and return a corrected complete function."
        )
    return code
