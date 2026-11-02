"""Example-driven Python function synthesis."""

import re

SYSTEM = (
    "You are an expert at inferring precise list transformations from examples. "
    "Pay close attention to indices, order, duplicates, ties, boundaries, and empty inputs."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation from ALL examples below. "
        "These tasks usually use a simple, uniform rule, not a lookup table. "
        "Consider adjacent pairs or triples, windows, runs, filtering, counting, "
        "and position-dependent operations where appropriate. Distinguish similar "
        "rules using every example, especially output length, ordering, duplicate "
        "values, and ties. Consider short or empty inputs and boundary conditions.\n\n"
        + examples
        + "\n\nReason carefully about the rule and verify it against each example. "
        "Then provide the complete standard-library-only Python implementation of "
        "`def f(xs):` in a final ```python code block. Return a list of ints."
    )
    try:
        reply = api.llm(prompt, system=SYSTEM)
    except api.BudgetExceeded:
        return "def f(xs):\n    return []\n"
    code = extract(reply)

    try:
        if api.budget().get("checks", 0) > 0:
            report = api.check(code)
            failed = [r for r in report if not r["passed"]]
        else:
            failed = []
    except (api.BudgetExceeded, Exception):
        failed = []

    if failed:
        feedback = "\n".join(
            f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
            for r in failed
        )
        repair = (
            prompt + "\n\nYour previous implementation was:\n```python\n" + code
            + "\n```\nIt failed these shown examples:\n" + feedback
            + "\nReconsider the rule, not just the failing cases. Return the corrected "
            "complete function in a final Python code block."
        )
        try:
            candidate = extract(api.llm(repair, system=SYSTEM))
            if api.budget().get("checks", 0) > 0:
                checked = api.check(candidate)
                if all(r["passed"] for r in checked):
                    return candidate
            else:
                return candidate
        except (api.BudgetExceeded, Exception):
            pass
    return code
