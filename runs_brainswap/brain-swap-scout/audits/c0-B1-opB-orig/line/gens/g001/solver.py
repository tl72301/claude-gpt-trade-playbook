"""Example-based solver with validation and repair."""

import re

SYSTEM = (
    "You infer concise, general Python list transformations from examples. "
    "Prioritize the simplest rule that explains every example, including ordering, "
    "duplicates, boundary cases, and whether a condition applies before or after "
    "a transformation. Do not hard-code examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^def f\s*\(", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended general rule and write `def f(xs):` mapping a list "
        "of integers to a list of integers. All examples must be satisfied.\n\n"
        + shown
        + "\n\nConsider competing explanations, especially filters versus index "
        "selection, strict versus inclusive thresholds, negative numbers, "
        "duplicates, output order, and transformations applied before or after "
        "filtering. Test your proposed rule against every example. Prefer a simple "
        "general rule, not a lookup table or a rule tailored to particular values. "
        "Handle empty and short inputs. Return only Python code in a fenced block."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if not candidate:
            break
        code = candidate
        try:
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
            "\n\nYour previous code was:\n```python\n" + code + "\n```\n"
            "It failed these examples:\n" + details
            + "\nReconsider the entire rule and return corrected code that "
            "satisfies all examples, not just the failures."
        )
    return code
