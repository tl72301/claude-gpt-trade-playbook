"""Infer a list transformation from examples and verify it before returning code."""

import re

SYSTEM = (
    "You are an expert at inferring small deterministic Python programs from examples. "
    "Prefer simple general rules over memorization. Be especially careful about "
    "ordering, duplicates, negative numbers, positions and empty inputs."
)


def extract(text):
    blocks = re.findall(
        r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE
    )
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:import |from |def f\s*\()", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended general transformation and implement def f(xs), "
        "returning a list of integers. Hidden inputs will differ; do not hardcode "
        "the examples.\n\n" + examples + "\n\n"
        "First reason about several competing rules and test each against every "
        "example, including empty outputs, repeated values and negative numbers. "
        "Notice whether output length, sorting and duplicates suggest filtering, "
        "a per-element mapping, or a positional or neighboring operation. "
        "Consider arithmetic and modular operations (including Python's behavior "
        "for negative numbers), divisibility, digits, bit counts, ranks, indices, "
        "cumulative values and combinations of these when appropriate. For sorted "
        "outputs, consider mapping each element first and then sorting. For filtered "
        "outputs, distinguish the selection criterion from the emitted value. "
        "Prefer the simplest consistent rule, but actively look for examples that "
        "distinguish superficially similar rules. Handle empty and short inputs. "
        "Use only the standard library. Return only executable code in a Python "
        "code block."
    )
    code = ""
    for _ in range(3):
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
            f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            "\n\nThe previous implementation was:\n```python\n" + code
            + "\n```\nIt failed these shown examples:\n" + details
            + "\nReconsider the underlying rule and test it against all examples, "
            "not just the failures. Return a complete corrected implementation."
        )
    return code
