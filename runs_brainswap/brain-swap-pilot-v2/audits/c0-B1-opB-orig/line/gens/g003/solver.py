"""Infer a list transformation from examples and verify it against them."""

import re

SYSTEM = (
    "You infer precise Python list transformations from examples. "
    "Prefer simple rules that explain every example and generalize to unseen inputs."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation and write def f(xs), returning a list "
        "of ints. Use all examples as constraints, including every omitted element "
        "and the output order.\n"
        "Before coding, compare plausible simple rules. Consider filters and "
        "maps in either order; values versus indices; original versus filtered "
        "positions; neighbors, counts, duplicates, and ordering. For each output, "
        "identify its possible source and mapping; check why nearby non-output "
        "elements are excluded. Check every candidate against every example.\n"
        "Pay particular attention to ambiguities that examples may not distinguish: "
        "positive versus nonnegative, strict versus inclusive bounds, parity and "
        "divisibility for negative numbers, endpoints, ties, and whether indices "
        "or values are returned. Prefer a simple conventional rule rather than "
        "an unnecessarily specific or memorized one. Handle empty and short "
        "inputs without mutating them.\n\n"
        + shown
        + "\n\nReturn the complete function in one Python code block."
    )
    code = ""
    for _ in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        try:
            if api.budget().get("checks", 0) <= 0:
                return code
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            "\n\nYour previous code was:\n```python\n" + code + "\n```\n"
            "It failed these examples:\n" + details
            + "\nReconsider the underlying rule against all examples, including "
            "excluded elements and output order. Return a corrected complete "
            "function in one Python code block."
        )
    return code
