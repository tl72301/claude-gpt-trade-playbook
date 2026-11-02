"""Infer a list transformation from examples and validate the proposed code."""

import re

SYSTEM = (
    "You are an expert at inferring simple list transformations from examples. "
    "Find a general rule, not a memorization of the examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended Python function f(xs), mapping a list of integers "
        "to a list of integers. Every example is exact.\n\n"
        + shown
        + "\n\nLook for a simple general rule, potentially combining filtering, "
        "mapping, indexing, ordering, or neighboring elements. Compare plausible "
        "rules against ALL examples, including output order and multiplicity. "
        "Be careful about zero, negative numbers, duplicates, empty lists, and "
        "strict versus inclusive boundaries. Do not assume a rule merely because "
        "it fits one example; prefer the simplest rule that explains all of them. "
        "Do not hard-code example inputs. Return executable Python code defining "
        "def f(xs), in a single Python code block."
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
        failures = [r for r in report if not r["passed"]]
        if not failures:
            return code
        details = "\n".join(
            f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
            for r in failures
        )
        prompt += (
            "\n\nYour previous code was:\n```python\n" + code
            + "\n```\nIt failed these examples:\n" + details
            + "\nReconsider the underlying rule, not just the failing cases. "
            "Return the complete corrected function in one Python code block."
        )
    return code
