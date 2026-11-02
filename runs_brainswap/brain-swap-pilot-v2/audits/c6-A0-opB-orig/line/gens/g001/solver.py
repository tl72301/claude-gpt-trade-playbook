"""Example-based Python function solver."""

import re

SYSTEM = (
    "You infer compact, general rules from input/output examples and write correct "
    "Python. Distinguish rules that agree on the examples but differ on boundary cases."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^def f\s*\(", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the simplest consistent transformation and implement `def f(xs):`.\n"
        "Examine all examples together. Consider filtering before mapping, positions "
        "and indices, adjacent elements, counts, arithmetic, order, and duplicates. "
        "For outputs that are small integers, consider whether they represent indices "
        "or counts rather than transformed input values. Check boundary distinctions "
        "such as positive versus nonnegative and strict versus inclusive comparisons. "
        "Consider multiple plausible rules internally; prefer the one that explains "
        "every detail without arbitrary exceptions. Avoid mutating the input.\n\n"
        + shown
        + "\n\nReturn only the implementation in one Python code block."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
            candidate = extract(reply)
            if candidate:
                code = candidate
            if not code:
                continue
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
            "\n\nThe previous implementation failed these examples:\n"
            + details
            + "\nReconsider the inferred rule, then return a corrected complete function."
        )
    return code
