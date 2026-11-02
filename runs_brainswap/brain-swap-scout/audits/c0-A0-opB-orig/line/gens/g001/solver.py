"""Example-based Python function synthesis."""

import re

SYSTEM = (
    "You infer simple, general list transformations from examples and write "
    "correct, standard-library-only Python. Do not overfit the examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended rule for def f(xs), mapping a list of integers to a "
        "list of integers. All examples are binding, but hidden inputs may include "
        "empty lists, duplicates, negative numbers, and boundary values.\n\n"
        f"{examples}\n\n"
        "Before coding, compare plausible rules against every example. Pay special "
        "attention to whether outputs are values, indices, counts, or transformed "
        "values; order and duplicate preservation; filtering before or after a "
        "transformation; strict versus inclusive boundaries; and positional or "
        "neighbor conditions. Prefer a simple coherent rule over special cases. "
        "Briefly explain your inference, then give the complete function in a "
        "single Python code block."
    )
    try:
        reply = api.llm(prompt, system=SYSTEM)
    except api.BudgetExceeded:
        return "def f(xs):\n    return []\n"

    code = extract(reply)
    report = None
    try:
        if api.budget().get("checks", 0) > 0:
            report = api.check(code)
    except api.BudgetExceeded:
        pass

    failed = [r for r in report if not r["passed"]] if report is not None else []
    review = (
        "Review this proposed solution independently for the examples below. "
        "The goal is to infer the intended general rule, not just fit the examples. "
        "Look for a simpler competing rule, overlooked negative values, boundary "
        "conditions, ordering, duplicate handling, and indices versus values. "
        "Do not change the rule on speculation alone; use the evidence in all "
        "examples. Return the best complete function in one Python code block.\n\n"
        f"{examples}\n\nProposed solution and reasoning:\n{reply}"
    )
    if failed:
        review += "\n\nThe proposed code fails these shown examples:\n" + "\n".join(
            f"input={r['input']!r}, expected={r['expected']!r}, actual={r['actual']!r}"
            for r in failed
        )

    try:
        if api.budget().get("llm_calls", 0) > 0:
            revised = extract(api.llm(review, system=SYSTEM))
            revised_report = None
            if api.budget().get("checks", 0) > 0:
                revised_report = api.check(revised)
            if revised_report is None or all(r["passed"] for r in revised_report):
                code = revised
            elif failed:
                if sum(r["passed"] for r in revised_report) > sum(r["passed"] for r in report):
                    code = revised
    except api.BudgetExceeded:
        pass
    return code
