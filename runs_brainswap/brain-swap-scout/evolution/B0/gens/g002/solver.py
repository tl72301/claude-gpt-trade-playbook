"""Infer a general list transformation from examples and verify candidates."""

import re

SYSTEM = (
    "You are an expert at inferring concise, general Python list transformations "
    "from input/output examples. Infer the intended rule rather than memorizing "
    "examples. Return executable Python using only the standard library."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = task.get("examples", [])
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in examples
    )
    prompt = (
        "Infer the single underlying deterministic rule for f(xs), where xs is a "
        "list of integers and the result is a list of integers.\n\n"
        f"All available examples:\n{shown}\n\n"
        "Consider several plausible simple rules before choosing. Pay particular "
        "attention to output length, ordering, duplicates, negative numbers, "
        "indices, adjacent elements, counts, and arithmetic. Distinguish rules "
        "that happen to agree on some examples. The function must generalize to "
        "unseen inputs, including empty or short lists when applicable. Do not "
        "hardcode examples or use the task ID. Return only a Python code block "
        "defining def f(xs)."
    )
    best = ""
    candidate = ""
    feedback = ""
    for attempt in range(3):
        try:
            if attempt == 0:
                request = prompt
            elif feedback:
                request = (
                    prompt + "\n\nThe previous candidate was:\n```python\n"
                    + candidate + "\n```\nIt failed these examples:\n"
                    + feedback
                    + "\nReconsider the underlying rule and return corrected code."
                )
            else:
                request = (
                    prompt + "\n\nA candidate that matches the shown examples is:\n"
                    "```python\n" + candidate + "\n```\n"
                    "Independently reconsider whether its rule is the simplest "
                    "general explanation of ALL examples. Look for subtle errors "
                    "in ordering, indexing, ties, and negative values. Return the "
                    "best complete function, retaining the candidate if its rule "
                    "is already the strongest explanation."
                )
            candidate = extract(api.llm(request, system=SYSTEM))
        except api.BudgetExceeded:
            break

        try:
            report = api.check(candidate)
        except api.BudgetExceeded:
            if not best:
                best = candidate
            break

        failed = [r for r in report if not r.get("passed")]
        if not failed:
            best = candidate
            feedback = ""
            if attempt >= 1:
                break
        else:
            feedback = "\n".join(
                f"f({r.get('input')!r}): expected {r.get('expected')!r}, "
                f"got {r.get('actual')!r}"
                for r in failed
            )
    return best or candidate
