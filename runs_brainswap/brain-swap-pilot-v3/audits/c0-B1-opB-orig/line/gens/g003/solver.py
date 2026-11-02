"""Example-driven Python function synthesis."""

import re

SYSTEM = (
    "You are an expert at inferring deterministic list transformations from examples. "
    "Prefer simple, general rules over memorization or arbitrary constants."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']}) == {ex['output']}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation from these complete examples:\n"
        + shown
        + "\n\nLook for rules involving positions, neighbors, ordering, filtering, "
        "arithmetic, cumulative values, and combinations of these. Consider multiple "
        "plausible rules before selecting the simplest one that explains ALL examples. "
        "Pay particular attention to duplicates, negative values, output length, and "
        "output order. Do not assume a pattern just because it fits one example. "
        "Handle empty and short inputs naturally. Avoid hardcoding examples.\n"
        "Return only Python code defining def f(xs): in a Python code block."
    )
    code = ""
    for attempt in range(3):
        try:
            code = extract(api.llm(prompt, system=SYSTEM))
        except api.BudgetExceeded:
            break
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"f({r['input']}) returned {r['actual']}; expected {r['expected']}"
            for r in failed
        )
        prompt += (
            "\n\nThe previous proposed code was:\n```python\n"
            + code
            + "\n```\nIt failed these examples:\n"
            + details
            + "\nReconsider the underlying rule and return corrected code only."
        )
    return code
