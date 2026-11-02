"""Infer a list transformation from examples and verify the generated code."""

import re

SYSTEM = (
    "You infer precise list transformations from examples and write correct Python. "
    "Distinguish values from indices, preserve ordering and multiplicity when indicated, "
    "and consider boundary cases. Use only the Python standard library."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^def f\s*\(", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']}) == {ex['output']}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended general rule for this list-of-integers transformation.\n"
        "Examine ALL examples jointly. Consider filtering, mapping, positions, "
        "neighbors, counts, ordering, and combinations of these. Prefer a simple "
        "rule that explains every output element and every omission, rather than "
        "a coincidence in one example. Pay special attention to strict versus "
        "inclusive thresholds, negative numbers, zero, duplicates, and empty lists.\n\n"
        + shown
        + "\n\nImplement def f(xs) returning a list of ints. "
        "Do not hard-code the examples. Return only Python code in a fenced block."
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
        details = "\n".join(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed
        )
        prompt += (
            "\n\nThe previous implementation was:\n```python\n"
            + code + "\n```\nIt failed these shown examples:\n"
            + details
            + "\nReconsider the rule using all examples and return corrected code."
        )
    return code
