"""Infer a list transformation from examples and verify it before returning."""

import re

SYSTEM = (
    "You infer precise, general Python list transformations from examples. "
    "Favor the simplest rule supported by all examples; do not memorize inputs."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.I)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^def f\s*\(", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    examples = task["examples"]
    shown = "\n".join(f"f({ex['input']!r}) == {ex['output']!r}" for ex in examples)
    prompt = (
        "Infer the intended transformation from these complete examples:\n"
        + shown
        + "\n\nConsider multiple plausible rules before choosing. Pay particular "
        "attention to whether output elements are values, indices, counts, or "
        "differences; filtering versus transforming; ordering; duplicates; signs; "
        "and strict versus inclusive boundaries. Use every example to distinguish "
        "competing hypotheses. Prefer a simple uniform rule that generalizes to "
        "empty lists and edge cases, not a lookup table. "
        "Briefly reason about the rule, then provide the complete standard-library "
        "Python implementation as the last fenced code block. Define def f(xs): "
        "and return a list of integers."
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
            f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
            for r in failed
        )
        prompt += (
            "\n\nThe following candidate failed the displayed examples:\n```python\n"
            + code + "\n```\n" + details
            + "\nReconsider the transformation rather than patching individual "
            "examples. Return a complete corrected function in a fenced code block."
        )
    return code
