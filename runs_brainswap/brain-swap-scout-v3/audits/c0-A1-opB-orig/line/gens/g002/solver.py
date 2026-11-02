"""Example-based Python function synthesizer."""
import re

SYSTEM = (
    "You infer precise list transformations from examples and write correct Python. "
    "Prefer simple, general rules supported by all examples; do not memorize examples."
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
        "Infer the intended transformation and implement def f(xs), returning a list "
        "of ints. Every example must match exactly, including order and duplicates.\n\n"
        + shown
        + "\n\nBefore coding, reason carefully about plausible competing rules. "
        "Separate filtering, indexing, ordering, and value transformations. Check "
        "whether conditions refer to original values, transformed values, indices, "
        "neighbors, or the whole list. Consider negative numbers, zero, duplicates, "
        "empty lists, and boundary positions. Do not assume a pattern from just one "
        "example. Choose the simplest rule explaining all examples, and verify it "
        "manually against every example. Output only the final code in a Python block."
    )
    code = ""
    feedback = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if not candidate:
            continue
        code = candidate
        try:
            if api.budget().get("checks", 0) <= 0:
                return code
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failures = [r for r in report if not r["passed"]]
        if not failures:
            return code
        feedback += (
            "\n\nThis implementation failed shown examples:\n"
            + "\n".join(
                f"f({r['input']!r}) returned {r['actual']!r}; "
                f"expected {r['expected']!r}" for r in failures
            )
            + "\nPrevious code:\n```python\n" + code
            + "\n```\nReconsider the inferred rule, then return corrected code."
        )
    return code
