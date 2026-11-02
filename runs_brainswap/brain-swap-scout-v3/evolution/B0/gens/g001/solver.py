"""Example-driven solver with verification and independent review."""

import re


SYSTEM = (
    "You infer precise list-to-list Python programs from examples. "
    "Prefer simple general rules over memorization. Return executable Python."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:from \S+ import .+|import \S+|def f\s*\()", text)
    return text[match.start():].strip() if match else text.strip()


def check(api, code):
    try:
        if api.budget().get("checks", 0) <= 0:
            return None
        return api.check(code)
    except Exception:
        return None


def failures(report):
    if report is None:
        return None
    return [r for r in report if not r.get("passed")]


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended general transformation from these examples and write "
        "def f(xs), returning a list of integers.\n\n" + examples + "\n\n"
        "Consider position-dependent operations, neighboring elements, counts, "
        "ordering, duplicates, signs, parity, and aggregations when appropriate. "
        "Check every example carefully, including ordering and ties. Avoid "
        "memorizing examples. Handle empty and short inputs naturally. "
        "Return only Python code in a fenced block."
    )
    try:
        first = extract(api.llm(prompt, system=SYSTEM))
    except api.BudgetExceeded:
        return "def f(xs):\n    return []\n"

    first_report = check(api, first)
    first_failed = failures(first_report)
    if api.budget().get("llm_calls", 0) <= 0:
        return first

    feedback = ""
    if first_failed:
        feedback = "\nThe implementation failed these shown examples:\n" + "\n".join(
            f"input={r.get('input')!r}, expected={r.get('expected')!r}, "
            f"actual={r.get('actual')!r}" for r in first_failed
        )
    review = (
        "Independently infer the most likely general rule for this programming "
        "task. Do not assume the candidate is correct just because it fits the "
        "examples. Compare plausible alternatives, especially strict versus "
        "non-strict comparisons, ties, positions, and output ordering. "
        "Use all examples; prefer a concise rule that explains each output.\n\n"
        + examples + "\n\nCandidate implementation:\n```python\n" + first
        + "\n```\n" + feedback
        + "\nReturn only your best corrected complete implementation of def f(xs) "
        "in one Python code block."
    )
    try:
        second = extract(api.llm(review, system=SYSTEM))
    except api.BudgetExceeded:
        return first

    second_report = check(api, second)
    second_failed = failures(second_report)
    if second_failed is None:
        return first if first_failed == [] else second
    if not second_failed:
        return second
    if first_failed == []:
        return first

    if api.budget().get("llm_calls", 0) > 0:
        correction = (
            "Fix this implementation to satisfy every example. Return only "
            "complete Python code defining f(xs).\n\n" + examples
            + "\n\nCode:\n```python\n" + second + "\n```\nFailures:\n"
            + "\n".join(
                f"{r.get('input')!r}: got {r.get('actual')!r}, "
                f"expected {r.get('expected')!r}" for r in second_failed
            )
        )
        try:
            third = extract(api.llm(correction, system=SYSTEM))
            third_failed = failures(check(api, third))
            if third_failed is None or not third_failed:
                return third
        except api.BudgetExceeded:
            pass
    if first_failed is not None and len(first_failed) < len(second_failed):
        return first
    return second
