"""Infer a general list transformation from examples."""
import re

SYSTEM = (
    "You are an expert at inferring concise Python list transformations. "
    "Generalize from all examples; do not memorize them."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended rule for a function f(xs) mapping a list of ints "
        "to a list of ints. All examples must hold.\n\n"
        + examples
        + "\n\nConsider several simple candidate rules before choosing one. "
        "Pay attention to positions versus values, adjacent pairs, filtering, "
        "duplicates, ordering, modular arithmetic, and cumulative operations. "
        "Check every element of every example, including negative numbers. "
        "Prefer a compact, uniform rule over special cases or memorization. "
        "If multiple rules fit, choose the most natural general rule. "
        "Return only complete Python code defining def f(xs), in a code block. "
        "Use only the standard library."
    )
    code = ""
    feedback = ""
    while api.budget().get("llm_calls", 0) > 0:
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if not candidate:
            break
        code = candidate
        if api.budget().get("checks", 0) <= 0:
            break
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r.get("passed")]
        if not failed:
            break
        details = "\n".join(
            f"f({r.get('input')!r}): expected {r.get('expected')!r}, "
            f"got {r.get('actual')!r}"
            for r in failed
        )
        feedback = (
            "\n\nThe following candidate failed the shown examples:\n```python\n"
            + code + "\n```\n" + details
            + "\nReconsider the rule from all examples and return corrected code only."
        )
    return code
