"""Infer a list transformation from examples and return Python source."""

import re

SYSTEM = (
    "You are an expert at inferring small Python programs from input/output examples. "
    "Identify the simplest general rule that explains every example, including edge "
    "cases. Do not assume a rule merely because it matches one example."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended deterministic transformation from these examples:\n"
        + examples
        + "\n\nBefore coding, compare plausible rules against ALL examples. "
        "Look closely at element values, positions, ordering, duplicates, signs, "
        "arithmetic, filtering, and list length. Prefer a simple rule that explains "
        "every output, not a coincidence or a special case. Consider empty inputs, "
        "negative numbers and repeated values. Do not hard-code the examples. "
        "Return only a Python code block defining def f(xs), using the standard library."
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
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        feedback = "\n".join(
            f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
            for r in failed
        )
        prompt += (
            "\n\nYour previous code was:\n```python\n" + code + "\n```\n"
            "It failed these examples:\n" + feedback
            + "\nReconsider the underlying rule, rather than patching individual "
            "examples. Return corrected code defining f."
        )
    return code
