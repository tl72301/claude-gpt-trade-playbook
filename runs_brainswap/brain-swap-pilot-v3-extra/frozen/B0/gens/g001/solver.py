"""Example-driven Python function solver."""

import re

SYSTEM = (
    "You infer simple list transformations from examples. Be precise about "
    "indices, filtering, order, duplicates, negative numbers, and empty inputs."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1]
    match = re.search(r"(?m)^def f\s*\(", text)
    return text[match.start():] if match else text


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended general rule for def f(xs), mapping a list of "
        "integers to a list of integers. All examples must be satisfied:\n"
        + shown
        + "\n\nBefore writing code, compare plausible rules rather than guessing "
        "from one example. Inspect how output length relates to input length: "
        "consider filtering individual elements, adjacent pairs or triples, "
        "sliding windows, and aggregation. Check whether outputs are values, "
        "indices, counts, differences, sums, remainders, or boolean indicators. "
        "Pay particular attention to negative numbers, repeated values, ordering, "
        "strict versus non-strict comparisons, and whether an operation is "
        "applied before or after filtering. Prefer a simple rule that explains "
        "every output element in every example, not a special case for the "
        "examples. Handle short and empty lists naturally.\n"
        "Briefly reason through the examples, then give the complete standalone "
        "function in a single Python code block. Use only the standard library."
    )
    code = ""
    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            reply = api.llm(prompt, system=SYSTEM)
            code = extract(reply)
            if api.budget().get("checks", 0) <= 0:
                return code
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r.get("passed")]
        if not failed:
            return code
        details = "\n".join(
            f"f({r.get('input')!r}): expected {r.get('expected')!r}, "
            f"got {r.get('actual')!r}"
            for r in failed
        )
        prompt += (
            "\n\nThe following candidate failed the shown examples:\n```python\n"
            + code + "\n```\n" + details
            + "\nReconsider the rule from scratch, checking all examples. "
            "Return a corrected complete function in a Python code block."
        )
    return code
