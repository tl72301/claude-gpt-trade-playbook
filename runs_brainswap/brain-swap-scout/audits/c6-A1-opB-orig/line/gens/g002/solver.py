"""Example-driven Python function solver."""

import re

SYSTEM = (
    "You infer concise, general Python list transformations from examples. "
    "Be precise about filtering, ordering, indexing, duplicates, and boundaries."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:def f\s*\(|import |from )", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation and write Python code defining "
        "`def f(xs):` returning a list of integers.\n\n"
        + shown
        + "\n\nConsider all examples together. Distinguish filtering by value "
        "from filtering by index, and consider operations on neighbors, "
        "positions, and consecutive pairs. Prefer a simple rule that explains "
        "every output exactly, including its length and order. Avoid assumptions "
        "that happen to fit only the displayed inputs. Handle empty inputs, "
        "duplicates, negative numbers, and boundary positions naturally. "
        "Use only the Python standard library. Return only code in a Python block."
    )
    try:
        code = extract(api.llm(prompt, system=SYSTEM))
    except api.BudgetExceeded:
        return "def f(xs):\n    return []\n"

    report = None
    try:
        if api.budget().get("checks", 0) > 0:
            report = api.check(code)
    except api.BudgetExceeded:
        pass

    failed = [r for r in report if not r["passed"]] if report is not None else []
    if api.budget().get("llm_calls", 0) > 0:
        feedback = ""
        if failed:
            feedback = "\nThe implementation failed these displayed examples:\n" + "\n".join(
                f"input {r['input']!r}: expected {r['expected']!r}, got {r['actual']!r}"
                for r in failed
            )
        else:
            feedback = (
                "\nReconsider whether the inferred rule generalizes beyond the "
                "examples. Examine plausible alternative rules and edge cases; "
                "correct any unjustified assumption. Keep the original if it is "
                "the best-supported interpretation."
            )
        revision_prompt = (
            prompt + "\n\nCurrent implementation:\n```python\n" + code
            + "\n```\n" + feedback
            + "\nReturn the complete best implementation, only in a Python block."
        )
        try:
            revised = extract(api.llm(revision_prompt, system=SYSTEM))
            if api.budget().get("checks", 0) > 0:
                revised_report = api.check(revised)
                revised_failures = sum(not r["passed"] for r in revised_report)
                if report is None or revised_failures <= len(failed):
                    code = revised
            elif failed or report is None:
                code = revised
        except api.BudgetExceeded:
            pass
    return code
