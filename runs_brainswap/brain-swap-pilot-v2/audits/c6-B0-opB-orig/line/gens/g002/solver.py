"""Example-based Python function synthesizer."""

import re

SYSTEM = (
    "Infer the simplest general list transformation supported by the examples. "
    "Think carefully about indexing, order, duplicates, boundary cases and negative "
    "numbers. Do not specialize to the examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer a Python function def f(xs) returning a list of ints.\n"
        "Examples:\n" + shown + "\n\n"
        "First reason about the rule before writing code. Compare plausible rules: "
        "selection by value versus index or neighbors, original versus transformed "
        "values, and operations on consecutive elements. Account for every output "
        "element and every omission, preserving order and multiplicity. Consider "
        "empty inputs, zero, negatives, duplicates, and edge positions. Prefer a "
        "simple consistent rule, not a lookup table. Return the final function "
        "in a Python code block."
    )
    try:
        reply = api.llm(prompt, system=SYSTEM)
    except api.BudgetExceeded:
        return "def f(xs):\n    return []"
    code = extract(reply)

    report = None
    if api.budget().get("checks", 0) > 0:
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            pass

    failed = [r for r in report if not r["passed"]] if report is not None else []
    if api.budget().get("llm_calls", 0) > 0:
        feedback = ""
        if failed:
            feedback = "\nThe proposed code fails these examples:\n" + "\n".join(
                f"input {r['input']!r}: got {r['actual']!r}, expected {r['expected']!r}"
                for r in failed
            )
        review = (
            prompt + "\n\nProposed solution:\n```python\n" + code + "\n```\n"
            + feedback
            + "\nIndependently review the inferred rule. Look for plausible simpler "
            "alternatives consistent with all examples, especially off-by-one "
            "indices, strict versus non-strict comparisons, filtering before versus "
            "after transformation, and unintended assumptions about input ranges. "
            "Correct the solution if needed; otherwise retain it. Return the complete "
            "final function in a Python code block."
        )
        try:
            revised = extract(api.llm(review, system=SYSTEM))
            if api.budget().get("checks", 0) > 0:
                revised_report = api.check(revised)
                if all(r["passed"] for r in revised_report):
                    return revised
                if report is not None and not failed:
                    return code
                if report is not None:
                    if sum(r["passed"] for r in revised_report) < sum(
                        r["passed"] for r in report
                    ):
                        return code
            return revised
        except api.BudgetExceeded:
            pass
    return code
