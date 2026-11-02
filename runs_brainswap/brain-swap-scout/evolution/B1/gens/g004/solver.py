"""Infer a list transformation from examples and validate the proposed code."""

import re

SYSTEM = (
    "You are an expert at inferring short deterministic Python programs from examples. "
    "Prefer a simple, general rule that explains every example, not a lookup table."
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
        "Infer the intended transformation from these examples. The input and output "
        "are lists of integers. Every example matters:\n\n"
        + shown
        + "\n\nBefore coding, reason carefully about output length, ordering, repeated "
        "values, negative numbers, and whether outputs depend on positions, neighbors, "
        "frequencies, comparisons, arithmetic, or a combination. Compare plausible "
        "rules against ALL examples, including duplicates and ties. Do not assume "
        "a rule merely because it matches one example. Prefer a concise, general "
        "transformation over special cases. Handle empty and short inputs naturally. "
        "Implement def f(xs) using only the Python standard library. "
        "Return only the complete Python code in a fenced Python block."
    )
    code = ""
    while True:
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if api.budget().get("checks", 0) <= 0:
            break
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            break
        if api.budget().get("llm_calls", 0) <= 0:
            break
        details = "\n".join(
            f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
            for r in failed
        )
        prompt += (
            "\n\nThe previous implementation failed these examples:\n"
            + details
            + "\nPrevious code:\n```python\n"
            + code
            + "\n```\nReconsider the underlying rule rather than patching individual "
            "examples. Return the corrected complete code."
        )
    return code
