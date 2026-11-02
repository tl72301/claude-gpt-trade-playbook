"""Infer a list transformation from examples and validate the proposed code."""

import re

SYSTEM = (
    "You infer concise, general Python list transformations from examples. "
    "Use all examples and prefer simple rules, but do not assume a rule without "
    "checking it against every example."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        "f(%r) == %r" % (example["input"], example["output"])
        for example in task["examples"]
    )
    prompt = (
        "Infer the intended deterministic transformation from lists of integers "
        "to lists of integers. Study ALL examples, including ordering, duplicates, "
        "negative values, and empty outputs. Consider multiple plausible rules "
        "before choosing the simplest rule that explains every example. Pay special "
        "attention to whether a condition applies to values, positions, adjacent "
        "pairs, or groups, and to the order of operations. Do not memorize examples.\n\n"
        + examples
        + "\n\nReturn only Python code defining def f(xs):. Use the standard library only."
    )
    best = ""
    feedback = ""
    while api.budget().get("llm_calls", 0) > 0:
        try:
            response = api.llm(prompt + feedback, system=SYSTEM)
            code = extract(response)
            if not code:
                break
            best = code
            if api.budget().get("checks", 0) <= 0:
                break
            results = api.check(code)
            failures = [r for r in results if not r["passed"]]
            if not failures:
                break
            feedback = "\n\nThe previous code failed shown examples:\n" + "\n".join(
                "f(%r) returned %r, expected %r"
                % (r["input"], r["actual"], r["expected"])
                for r in failures
            ) + "\nReconsider the rule and return corrected code only."
        except api.BudgetExceeded:
            break
    return best
