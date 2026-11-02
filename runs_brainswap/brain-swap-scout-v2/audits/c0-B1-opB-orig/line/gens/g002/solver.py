"""Infer a list transformation from examples."""
import re

SYSTEM = (
    "You infer small deterministic Python list transformations from examples. "
    "Prefer simple, general rules and carefully distinguish plausible alternatives."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended rule for a function f(xs), where xs and the result "
        "are lists of integers. All examples must be satisfied:\n\n"
        + shown
        + "\n\nConsider competing simple rules, including boundary cases, "
        "ordering, duplicates, filtering versus indexing, and operations composed "
        "in different orders. Do not assume a property merely because it happens "
        "to hold in a few examples. Choose the simplest rule that explains all "
        "examples and is likely to generalize. Return only Python code defining "
        "def f(xs), in a single fenced Python block. Use only the standard library."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if api.budget().get("checks", 0) <= 0:
            return code
        try:
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
            "\n\nThe previous implementation failed these examples:\n"
            + details
            + "\nPrevious code:\n```python\n"
            + code
            + "\n```\nReconsider the rule and return corrected code only."
        )
    return code
