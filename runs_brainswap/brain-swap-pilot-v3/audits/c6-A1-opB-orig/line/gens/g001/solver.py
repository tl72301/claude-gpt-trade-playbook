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
        f"f({ex['input']}) == {ex['output']}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation and implement def f(xs), returning a "
        "list of integers. All examples must match exactly, including order and "
        "duplicates.\n\n" + shown + "\n\n"
        "Before writing code, compare plausible rules against every example. "
        "Consider elementwise filters and mappings, adjacent pairs or windows, "
        "indices, sorting, and concatenated passes when relevant. Distinguish "
        "strict from non-strict comparisons, value from index, and input order "
        "from sorted order. Avoid assumptions not supported by the examples. "
        "Handle empty and short lists naturally. Return only code in a Python block."
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
            f"f({r['input']}) returned {r['actual']}; expected {r['expected']}"
            for r in failed[:4]
        )
        prompt += (
            f"\n\nAttempt {attempt + 1}:\n```python\n{code}\n```\n"
            f"It failed these shown examples:\n{details}\n"
            "Reconsider the rule and fix the implementation. Return only the "
            "complete corrected function in a Python block."
        )
    return code
