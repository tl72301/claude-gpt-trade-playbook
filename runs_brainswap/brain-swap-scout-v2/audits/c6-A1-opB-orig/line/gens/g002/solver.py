"""Infer a list transformation from examples and verify it on shown cases."""

import re

SYSTEM = (
    "You infer small Python list transformations from examples. Prefer simple, "
    "general rules, and distinguish rules that coincide on the given examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:from \S+ import .+\n|import .+\n|def f\s*\()", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Write def f(xs): returning a list of ints, consistent with ALL examples.\n"
        "Infer the simplest general transformation, not a lookup table. Consider "
        "filtering before mapping, adjacent pairs, indices, ordering, duplicates, "
        "and whether output length can change. Compare plausible alternative rules "
        "against every example, especially boundary cases such as zero, negatives, "
        "and repeated values. Do not assume a rule merely because it fits one case.\n\n"
        + shown
        + "\n\nReturn only executable Python code in a single Python code block."
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
            f"f({r['input']!r}): got {r['actual']!r}, expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            f"\n\nPrevious code:\n```python\n{code}\n```\n"
            f"It failed these shown cases:\n{details}\n"
            "Reconsider the rule and return corrected code that satisfies all examples."
        )
    return code
