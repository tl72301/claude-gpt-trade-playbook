"""Infer a list transformation from examples and validate proposed code."""

import re

SYSTEM = (
    "You infer precise Python list transformations from examples. Prefer simple, "
    "general rules supported by all examples; do not assume a rule from one example."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    code = blocks[-1] if blocks else text
    return code.strip()


def solve(task, api):
    examples = task["examples"]
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in examples
    )
    prompt = (
        "Infer the intended transformation and implement def f(xs), returning a list "
        "of integers. All examples must match exactly.\n\n"
        + shown
        + "\n\nFirst reason carefully about several possible rules. In particular, "
        "determine separately what selects elements or positions, how output values "
        "are computed, their ordering, and the output length. Consider adjacent "
        "pairs, indices, filtering, duplicates, and arithmetic where appropriate. "
        "Check every output against every input, including empty outputs. Avoid "
        "overfitting to accidental properties of a single example. Then return "
        "only the final implementation in a Python code block."
    )
    best_code = ""
    best_passed = -1
    feedback = ""
    for attempt in range(3):
        try:
            if attempt == 0:
                query = prompt
            else:
                query = (
                    prompt
                    + "\n\nPrevious candidate:\n```python\n"
                    + best_code
                    + "\n```\n"
                    + feedback
                    + "\nIndependently reconsider the rule, especially selection, "
                    "ordering and length. Look for a simpler alternative that explains "
                    "ALL examples, not just the checked cases. Fix any mismatch. "
                    "Return the complete code in a Python block."
                )
            code = extract(api.llm(query, system=SYSTEM))
        except api.BudgetExceeded:
            break

        if not code:
            continue
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            if not best_code:
                best_code = code
            break
        passed = sum(bool(r.get("passed")) for r in report)
        if passed > best_passed:
            best_code, best_passed = code, passed
        failed = [r for r in report if not r.get("passed")]
        if failed:
            feedback = "\n".join(
                f"Check: f({r.get('input')!r}) returned {r.get('actual')!r}; "
                f"expected {r.get('expected')!r}."
                for r in failed
            )
        else:
            feedback = (
                "The candidate passes the shown examples, but hidden cases may "
                "distinguish different plausible rules."
            )
            if attempt >= 1:
                # Prefer the independently reviewed candidate when both fit.
                best_code = code
                break

    return best_code or "def f(xs):\n    return []\n"
