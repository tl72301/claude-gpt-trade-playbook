"""Example-driven solver. Standard library only."""

import re

SYSTEM = (
    "You infer compact deterministic list transformations from examples. "
    "Be precise about indices, ordering, duplicates, negative numbers, and boundary cases."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended rule for a Python function f(xs) mapping a list of "
        "integers to a list of integers.\n\n"
        + shown
        + "\n\nConsider several plausible rules before choosing. Use every example, "
        "including output order, multiplicity, and length, to discriminate them. "
        "Consider transformations involving positions, adjacent elements, arithmetic "
        "and modular arithmetic as well as filtering and sorting. Prefer a simple "
        "general rule over memorizing examples or accidental numeric thresholds. "
        "Handle empty lists, negatives and duplicates naturally. Verify the proposed "
        "code mentally against all examples. Return only executable Python code "
        "defining def f(xs), in a single python code block."
    )
    code = ""
    for attempt in range(3):
        try:
            code = extract(api.llm(prompt, system=SYSTEM))
        except api.BudgetExceeded:
            break
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failures = [r for r in report if not r["passed"]]
        if not failures:
            return code
        details = "\n".join(
            f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
            for r in failures
        )
        prompt += (
            "\n\nThe previous code was:\n```python\n" + code
            + "\n```\nIt failed these examples:\n" + details
            + "\nReconsider the rule, not just the implementation. Return corrected code."
        )
    return code
