"""Synthesize a list-to-list function from input/output examples."""

import re

SYSTEM = (
    "You infer simple, general Python list transformations from examples. "
    "Be precise about boundary cases, ordering, duplicates, and indices."
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
        "Infer the intended transformation and write Python code defining "
        "`def f(xs):` returning a list of ints.\n\n"
        f"{shown}\n\n"
        "Consider multiple simple hypotheses before choosing one. Check each "
        "against every example, including output order, repeated values, whether "
        "outputs are values or indices, adjacent relationships, and conditions "
        "at the ends of the list. Prefer a simple rule that explains all the "
        "data without arbitrary special cases. Handle empty and short inputs. "
        "Return only the code in a Python fenced block."
    )
    best = ""
    best_passed = -1
    feedback = ""

    while api.budget().get("llm_calls", 0) > 0:
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not code:
            break

        if api.budget().get("checks", 0) <= 0:
            return best if best_passed >= 0 else code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return best if best_passed >= 0 else code

        passed = sum(bool(r.get("passed")) for r in report)
        if passed > best_passed:
            best, best_passed = code, passed
        failures = [r for r in report if not r.get("passed")]
        if not failures:
            return code

        details = "\n".join(
            f"f({r.get('input')!r}): expected {r.get('expected')!r}, "
            f"got {r.get('actual')!r}"
            for r in failures
        )
        feedback = (
            "\n\nThe following candidate failed the displayed examples:\n"
            f"```python\n{code}\n```\n{details}\n"
            "Reconsider the rule and return a corrected complete function. "
            "Do not special-case the examples."
        )

    return best

