"""Infer a list transformation from examples and return Python source."""

import re

SYSTEM = (
    "You infer precise list transformations from input/output examples and write "
    "small, correct Python functions. Prefer simple rules supported by all examples."
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
        "list of integers. All examples must match exactly, including order and "
        "duplicates.\n\n" + shown + "\n\n"
        "Before coding, compare plausible rules against every example. Look at "
        "output lengths, ordering, repeated values, and how each output relates "
        "to the input. Consider filters and mappings, indices, adjacent pairs and "
        "windows, counts and ranks, sorting, cumulative or stateful operations, "
        "and concatenated passes where relevant. Check boundaries and strict "
        "versus non-strict comparisons. If several rules fit, prefer a simple, "
        "consistent rule over special cases or memorizing the examples. Handle "
        "empty and short lists naturally. Return only the complete function in "
        "a Python block."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
            for r in failed[:4]
        )
        prompt += (
            f"\n\nAttempt {attempt + 1}:\n```python\n{code}\n```\n"
            f"It failed these shown examples:\n{details}\n"
            "Reconsider the underlying rule, not just the individual failures, "
            "and verify the revision against all examples. Return only the "
            "complete corrected function in a Python block."
        )
    return code
