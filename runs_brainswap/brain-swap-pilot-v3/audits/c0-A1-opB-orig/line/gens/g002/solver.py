"""Infer a list transformation from examples."""
import re

SYSTEM = """You are an expert at inferring small Python programs from examples.
Find a simple, general rule, not a lookup table. Consider filtering, arithmetic,
ordering, rotations, indices, duplicates, and combinations of these operations.
Account for every element and the exact order of each output. Prefer rules that
explain all examples without special cases. Return executable Python code only."""

def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text

def solve(task, api):
    shown = "\n".join(
        "f(%r) == %r" % (ex["input"], ex["output"])
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation and write def f(xs), returning a list "
        "of ints. Analyze the examples carefully, especially selection and output "
        "order; do not memorize the examples. Check your proposed rule against "
        "every example before answering.\n\n" + shown +
        "\n\nReturn only the function in a Python code block."
    )
    code = ""
    for attempt in range(3):
        try:
            code = extract(api.llm(prompt, system=SYSTEM))
        except api.BudgetExceeded:
            break
        if api.budget().get("checks", 0) <= 0:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            "f(%r) returned %r, expected %r" %
            (r["input"], r["actual"], r["expected"])
            for r in failed
        )
        prompt += (
            "\n\nYour previous code was:\n" + code +
            "\nIt failed these examples:\n" + details +
            "\nReconsider the rule and return corrected code."
        )
    return code
