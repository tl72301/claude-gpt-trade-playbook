"""Infer a list transformation from examples, checking candidate implementations."""

import re

SYSTEM = (
    "You are an expert at inferring small deterministic Python programs from "
    "input/output examples. Prefer simple, general rules over memorization. "
    "Check every proposed rule against every example before coding."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation from these examples:\n" + shown +
        "\n\nConsider several plausible rules, including index-based operations, "
        "neighboring pairs or windows, frequencies, ranks, arithmetic, filtering, "
        "and order-dependent operations. Use all examples to distinguish them; "
        "do not assume the first pattern you notice is correct. Think carefully "
        "about duplicates, negative numbers, output length, ordering, and ties. "
        "Choose the simplest rule that explains every example and generalizes "
        "to unseen inputs, including empty and short lists. Implement it as "
        "`def f(xs):` using only the Python standard library. Return only code "
        "in a Python fenced block."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if candidate:
            code = candidate
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"f({r['input']!r}): got {r['actual']!r}, expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            f"\n\nThe previous implementation was:\n```python\n{code}\n```\n"
            f"It failed these examples:\n{details}\n"
            "Reconsider the underlying rule, not just the implementation. "
            "Produce a corrected complete function consistent with all examples."
        )
    return code
