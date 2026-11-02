"""Infer list transformations from examples, then review and check the code."""

import re

SYSTEM = (
    "You infer compact Python list transformations from examples. "
    "Be precise about ordering, duplicates, boundaries, and negative numbers."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    pos = text.find("def f(")
    return text[pos:].strip() if pos >= 0 else text.strip()


def solve(task, api):
    examples = "\n".join(
        "f(%r) == %r" % (e["input"], e["output"])
        for e in task["examples"]
    )
    prompt = (
        "Infer the intended general rule for f, not merely a solution that "
        "memorizes the examples. The input and output are lists of integers.\n\n"
        + examples
        + "\n\nConsider simple compositions of filtering, mapping, adjacent "
        "pairs, positions or indices, arithmetic, and order-dependent operations. "
        "Use every example to distinguish competing rules. Avoid unjustified "
        "assumptions about empty inputs, duplicates, signs, or ordering. "
        "Return only Python code defining def f(xs), in a fenced Python block."
    )
    try:
        code = extract(api.llm(prompt, system=SYSTEM))
    except api.BudgetExceeded:
        return "def f(xs):\n    return []"

    # A separate review can catch rules that fit the visible examples but use
    # the wrong threshold, indices, ordering, or operation on hidden inputs.
    try:
        review = (
            "Review this proposed solution independently against all examples. "
            "First infer the most plausible simple general rule, considering "
            "alternatives and edge cases. Pay particular attention to whether "
            "outputs represent values, indices, or results of a sequence of "
            "operations. Fix any errors or unjustified assumptions. "
            "If the proposed solution is already the best-supported rule, keep it.\n\n"
            + examples
            + "\n\nProposed code:\n```python\n"
            + code
            + "\n```\n\nReturn only the complete corrected Python code in a "
            "fenced block defining def f(xs)."
        )
        reviewed = extract(api.llm(review, system=SYSTEM))
        if "def f(" in reviewed:
            code = reviewed
    except api.BudgetExceeded:
        pass

    # Check visible examples and use remaining calls to repair actual failures.
    while True:
        try:
            budget = api.budget()
            if budget.get("checks", 0) <= 0:
                break
            results = api.check(code)
        except api.BudgetExceeded:
            break
        failures = [r for r in results if not r["passed"]]
        if not failures:
            break
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            repair = (
                "The following code failed the examples. Infer and implement the "
                "general rule, not a lookup table.\n\n"
                + examples
                + "\n\nCode:\n```python\n"
                + code
                + "\n```\n\nFailures:\n"
                + "\n".join(
                    "input=%r expected=%r actual=%r"
                    % (r["input"], r["expected"], r["actual"])
                    for r in failures
                )
                + "\n\nReturn only complete Python code defining def f(xs) "
                "in a fenced block."
            )
            candidate = extract(api.llm(repair, system=SYSTEM))
            if "def f(" not in candidate:
                break
            code = candidate
        except api.BudgetExceeded:
            break
    return code
