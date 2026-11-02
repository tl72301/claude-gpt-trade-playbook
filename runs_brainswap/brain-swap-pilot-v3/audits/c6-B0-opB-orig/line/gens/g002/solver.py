"""Example-driven Python function synthesizer."""

import re

SYSTEM = (
    "Infer general list transformations from examples. Favor simple rules "
    "that explain every example and generalize to unseen inputs. "
    "Return executable Python, not example-specific lookup tables."
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
        "Infer the intended general transformation and write def f(xs), "
        "returning a list of ints.\n\n"
        + shown
        + "\n\nAnalyze all examples before coding. Consider multiple plausible "
        "rules and reject any that cannot account for every output, including "
        "empty outputs, ordering, and repeated values. For each output element "
        "consider what input element, position, group, or aggregate produced it; "
        "do not assume it must be a transformed input value. Consider filtering, "
        "arithmetic, sorting, reversing, deduplication, cumulative operations, "
        "adjacent elements, grouping and frequencies, and compositions of these. "
        "Check whether counts refer to the original list or a filtered list, "
        "and whether groups are ordered by value or first occurrence. "
        "Distinguish competing rules using negative numbers, duplicates, and "
        "all available examples. Prefer a concise general rule over constants "
        "or special cases fitted to the examples. Handle empty lists and other "
        "integer inputs naturally. Return the final function in a single "
        "Python code block."
    )
    code = ""
    while api.budget().get("llm_calls", 0) > 0:
        try:
            candidate = extract(api.llm(prompt, system=SYSTEM))
        except api.BudgetExceeded:
            break
        if not candidate:
            break
        code = candidate
        if api.budget().get("checks", 0) <= 0:
            return code
        try:
            report = api.check(candidate)
        except api.BudgetExceeded:
            return code
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
            + "\n```\nReconsider the whole rule rather than patching individual "
            "cases. Compare alternative interpretations of the output, including "
            "counts and positions. Return corrected code in a Python block."
        )
    return code
