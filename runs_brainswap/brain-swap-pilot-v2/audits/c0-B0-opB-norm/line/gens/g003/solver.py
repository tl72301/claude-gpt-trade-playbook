"""Infer a simple list transformation from examples and verify the implementation."""
import re

SYSTEM = (
    "You are an expert at inferring small Python list transformations from examples. "
    "Prefer the simplest consistent rule, but distinguish carefully between plausible "
    "rules. Return executable standard-library Python."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        "f(%r) == %r" % (e["input"], e["output"]) for e in task["examples"]
    )
    prompt = (
        "Infer the intended deterministic transformation and implement def f(xs) "
        "returning a list of ints.\n\n"
        + examples
        + "\n\nBefore writing code, compare several simple hypotheses against ALL "
        "examples. Consider filtering by sign, parity, divisibility or range; mapping "
        "values; indices rather than values; adjacent pairs or differences; counts, "
        "remainders and grouping. Check ordering, duplicates, zero, negatives, and "
        "boundary conditions. Do not assume a rule just because it fits one example. "
        "Prefer a simple composition of common operations over memorizing examples. "
        "Mentally run your final rule on every example. Return only the function code "
        "in a Python fenced block."
    )
    code = "def f(xs):\n    return []\n"
    for attempt in range(3):
        try:
            code = extract(api.llm(prompt, system=SYSTEM))
        except api.BudgetExceeded:
            break
        try:
            failures = [r for r in api.check(code) if not r["passed"]]
        except api.BudgetExceeded:
            break
        if not failures:
            return code
        details = "\n".join(
            "f(%r): expected %r, got %r" % (r["input"], r["expected"], r["actual"])
            for r in failures
        )
        prompt += (
            "\n\nThe previous implementation was:\n```python\n" + code
            + "\n```\nIt failed these examples:\n" + details
            + "\nReconsider the underlying rule, then return corrected code only."
        )
    return code
