"""Infer a list transformation from examples and validate it when possible."""

import re

SYSTEM = (
    "You infer precise Python list transformations from examples. "
    "Prefer a simple rule that explains every example, including ordering, "
    "duplicates, negative values, and boundary cases."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended deterministic transformation from these examples:\n"
        + shown
        + "\n\nConsider several plausible rules before choosing one. Check the "
        "entire input and output of every example, particularly output ordering, "
        "index-dependent operations, sorting, filtering, duplicates, modular "
        "arithmetic, and negative numbers. Do not hard-code the examples. "
        "Implement the simplest rule consistent with all examples. Handle empty "
        "and short lists naturally. Return only Python code defining def f(xs), "
        "in a single fenced code block."
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
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            "\n\nThe previous implementation was:\n```python\n"
            + code + "\n```\nIt failed these checks:\n" + details
            + "\nReconsider the underlying rule rather than patching individual "
            "examples. Return a complete corrected function."
        )
    return code
