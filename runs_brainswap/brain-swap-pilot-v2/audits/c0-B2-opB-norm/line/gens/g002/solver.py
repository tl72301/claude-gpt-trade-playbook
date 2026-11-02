"""Infer a list transformation from examples and verify it."""
import re

SYSTEM = (
    "You infer precise Python list transformations from examples. "
    "Prefer simple, general rules over memorizing examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation and write def f(xs) returning a list of ints.\n"
        "All examples must match exactly, including order and duplicates. "
        "Consider compositions of filtering, mapping, reversing, sorting, indexing, "
        "and aggregation. Distinguish conditions on original values from conditions "
        "on transformed values; check negative numbers, zero, ties, and empty lists. "
        "Choose the simplest rule that explains all examples, not a lookup table. "
        "Think through competing rules and edge cases before coding.\n\n"
        + examples
        + "\n\nReturn only Python code in a single fenced block."
    )
    code = ""
    for attempt in range(3):
        try:
            code = extract(api.llm(prompt, system=SYSTEM))
        except api.BudgetExceeded:
            break
        try:
            results = api.check(code)
        except api.BudgetExceeded:
            break
        failures = [r for r in results if not r["passed"]]
        if not failures:
            return code
        feedback = "\n".join(
            f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
            for r in failures
        )
        prompt += (
            "\n\nYour previous code was:\n```python\n" + code + "\n```\n"
            "It failed these examples:\n" + feedback
            + "\nReconsider the inferred rule and return corrected code only."
        )
    return code
