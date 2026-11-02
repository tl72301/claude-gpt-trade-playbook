"""Example-driven Python function synthesizer."""

import re

SYSTEM = (
    "You infer general list transformations from examples. "
    "Prefer simple rules that explain every example, including ordering and duplicates."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = task.get("examples", [])
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in examples
    )
    prompt = (
        "Infer the intended general transformation and write def f(xs): "
        "returning a list of ints.\n\n"
        + shown
        + "\n\nBefore coding, consider simple compositions of operations: filtering, "
        "elementwise arithmetic (including modulo and integer division), sorting, "
        "reversing, deduplication, cumulative sums, and selecting by value or index. "
        "Check the order of operations and whether output order follows the input. "
        "Distinguish rules using negative values, duplicates, and all examples. "
        "Avoid assumptions that only happen to hold for the displayed values. "
        "Handle empty lists and other integer inputs naturally. "
        "Return the final function in a single Python code block."
    )
    code = ""
    last_passing = ""
    while api.budget().get("llm_calls", 0) > 0:
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if not candidate:
            break
        code = candidate
        if api.budget().get("checks", 0) <= 0:
            return last_passing or code
        try:
            report = api.check(candidate)
        except api.BudgetExceeded:
            return last_passing or code
        failed = [r for r in report if not r.get("passed")]
        if not failed:
            return candidate
        details = "\n".join(
            f"f({r.get('input')!r}): expected {r.get('expected')!r}, "
            f"got {r.get('actual')!r}"
            for r in failed
        )
        prompt += (
            "\n\nThe previous function failed these displayed examples:\n"
            + details
            + "\nPrevious code:\n```python\n"
            + candidate
            + "\n```\nReconsider the whole rule, not just these cases. "
            "Return corrected code in a Python block."
        )
    return last_passing or code
