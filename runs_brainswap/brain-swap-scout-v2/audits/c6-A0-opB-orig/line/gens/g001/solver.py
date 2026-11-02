"""Example-driven Python function synthesizer."""

import re

SYSTEM = (
    "You infer compact Python list transformations from examples. "
    "Return executable standard-library Python, not an explanation."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return (blocks[-1] if blocks else text).strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended general rule and implement `def f(xs):`, returning "
        "a list of ints. All examples must match exactly, including order and "
        "duplicates:\n\n" + shown + "\n\n"
        "Consider both values and zero-based indices: filtering by a property, "
        "mapping values or indices, neighboring elements, sorting, and combinations "
        "of these. Pay particular attention to boundaries, negative numbers, "
        "zero, duplicates, and whether a condition is strict. Compare plausible "
        "rules against ALL examples; prefer a simple general rule rather than "
        "memorizing examples. Check the proposed code manually against each example. "
        "Output only code in one Python block, with a top-level def f(xs)."
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
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        feedback = "\n".join(
            f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
            for r in failed
        )
        prompt += (
            "\n\nYour previous code was:\n```python\n" + code + "\n```\n"
            "It failed these shown examples:\n" + feedback +
            "\nReconsider the rule and fix the code. Return the complete function."
        )
    return code
