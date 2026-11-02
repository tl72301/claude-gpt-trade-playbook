"""Example-driven Python function synthesizer."""

import re

SYSTEM = (
    "You infer precise list transformations from examples and write correct Python. "
    "Prefer the simplest rule supported by all examples, not memorization."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:import |from |def f\()", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    examples = "\n".join(
        "f(%r) == %r" % (example["input"], example["output"])
        for example in task["examples"]
    )
    prompt = (
        "Infer the intended general transformation from ALL examples below. "
        "The output is a list of integers. Consider combinations of filtering, "
        "mapping, ordering, indexing, adjacent pairs, and operations applied in "
        "sequence. Distinguish conditions on original values from conditions on "
        "transformed values; check boundaries, duplicates, negative numbers, "
        "and whether ordering is preserved. Compare plausible rules against every "
        "example and choose the simplest consistent general rule. Do not hardcode "
        "the examples. Return only Python code defining def f(xs), using only the "
        "standard library.\n\n" + examples
    )
    code = ""
    while True:
        try:
            response = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(response)
        try:
            results = api.check(code)
        except api.BudgetExceeded:
            break
        failures = [result for result in results if not result["passed"]]
        if not failures:
            break
        details = "\n".join(
            "f(%r): expected %r, got %r" %
            (item["input"], item["expected"], item["actual"])
            for item in failures
        )
        prompt += (
            "\n\nThe following implementation failed shown examples:\n"
            + code + "\nFailures:\n" + details
            + "\nReconsider the rule and return a complete corrected implementation."
        )
    return code
