"""Example-driven solver with validation and repair."""

import re

SYSTEM = (
    "You infer concise Python list transformations from examples. "
    "Consider competing rules and edge cases; do not assume a rule from one example."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended general transformation from ALL examples below. "
        "Distinguish element values from indices, and check filtering, ordering, "
        "duplicates, negative numbers, and boundary cases. Consider plausible "
        "alternative rules and choose the simplest one consistent with every example. "
        "Implement it using only the Python standard library.\n\n"
        + shown
        + "\n\nReturn only Python code defining def f(xs), which returns a list of ints."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
            code = extract(reply)
            report = api.check(code)
        except api.BudgetExceeded:
            break
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
            + "\nReconsider the underlying rule, not just these individual cases. "
            "Return only corrected Python code defining def f(xs)."
        )
    return code
