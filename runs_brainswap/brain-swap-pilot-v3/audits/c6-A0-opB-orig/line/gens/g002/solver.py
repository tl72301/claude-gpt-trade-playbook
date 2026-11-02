"""Solve list-transformation tasks using examples and feedback."""

import re

SYSTEM = (
    "You are an expert at inferring compact Python list transformations from examples. "
    "Distinguish the intended general rule from accidental matches."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:from |import |def f\s*\()", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the simplest general rule for this list-of-integers transformation:\n"
        + shown
        + "\n\nConsider multiple plausible rules before choosing one. Check the rule "
        "against every example, including order and duplicates. Consider whether values "
        "or positions are being filtered, transformed, aggregated, or sorted; do not "
        "assume a familiar rule merely because it matches one example. Handle empty "
        "lists and edge cases. Use only the Python standard library. Return only a "
        "Python code block defining def f(xs), with no example-specific lookup tables."
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
            f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            f"\n\nPrevious code:\n```python\n{code}\n```\n"
            f"It failed these examples:\n{feedback}\n"
            "Reconsider the underlying rule and return corrected code."
        )
    return code
