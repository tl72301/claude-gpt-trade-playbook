"""Example-driven Python function synthesis."""

import re

SYSTEM = (
    "You infer precise list transformations from examples and write correct Python. "
    "Prioritize simple general rules over memorizing examples."
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
        "Infer the intended list transformation from all examples below. "
        "Consider operations such as filtering, mapping, slicing, reversing, "
        "sorting, deduplication, and compositions of these. Pay particular "
        "attention to order, duplicates, zero, negative values, and whether "
        "a condition applies before or after a transformation. Compare plausible "
        "rules and choose the simplest rule that explains every example; do not "
        "memorize the examples. Handle empty and short lists naturally.\n\n"
        f"{examples}\n\n"
        "Return only Python code defining def f(xs): in a Python code block."
    )
    code = ""
    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            code = extract(api.llm(prompt, system=SYSTEM))
        except api.BudgetExceeded:
            break

        try:
            if api.budget().get("checks", 0) <= 0:
                return code
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [item for item in report if not item["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"f({item['input']!r}): got {item['actual']!r}, "
            f"expected {item['expected']!r}"
            for item in failed
        )
        prompt += (
            f"\n\nPrevious code:\n```python\n{code}\n```\n"
            f"It failed these examples:\n{details}\n"
            "Reconsider the entire rule, not just these individual cases. "
            "Return a complete corrected function."
        )
    return code
