"""Infer a list transformation from examples and return Python source."""
import re

SYSTEM = (
    "You are an expert at inferring compact list transformations from examples. "
    "Prefer simple, general rules over memorization. Output executable Python."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation from these examples. "
        "The input and output are lists of integers.\n\n"
        f"{shown}\n\n"
        "Consider filtering, mapping, sorting, indexing, adjacent pairs, and "
        "combinations of these. Distinguish rules that agree on the examples but "
        "differ on edge cases, such as zero, duplicates, ordering and empty lists. "
        "Check every example carefully. Prefer the simplest consistent general rule, "
        "not a lookup table. Implement it with the Python standard library only. "
        "Return only a Python code block defining def f(xs)."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
            code = extract(reply)
            if api.budget().get("checks", 0) <= 0:
                return code
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            f"\n\nYour previous code:\n```python\n{code}\n```\n"
            f"It failed these examples:\n{details}\n"
            "Reconsider the rule and return corrected code. Ensure it satisfies "
            "all examples, not just the failures."
        )
    return code
