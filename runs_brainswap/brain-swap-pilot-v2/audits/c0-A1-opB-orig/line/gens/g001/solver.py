"""Infer a list transformation from examples."""
import re

SYSTEM = """You are an expert at inferring short, general Python list transformations.
Infer the intended rule, not a lookup table. Examples may be ambiguous: compare
plausible rules against every example and prefer a simple, consistent composition
of filtering, mapping, ordering, indexing, or aggregation operations."""

def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text

def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Write def f(xs): returning a list of ints. Infer the same general rule "
        "for all examples, including unseen inputs.\n\n" + shown +
        "\n\nBefore coding, consider alternative explanations and test them against "
        "every example. Pay attention to operation order, original versus filtered "
        "indices, duplicates, negative values, strict boundaries, and whether output "
        "order follows input order. Avoid assumptions not supported by examples. "
        "Handle empty inputs and edge cases. Return only Python code in a fenced block."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
            candidate = extract(reply)
            code = candidate
            if api.budget().get("checks", 0) <= 0:
                break
            report = api.check(candidate)
            failed = [r for r in report if not r["passed"]]
            if not failed:
                break
            details = "\n".join(
                f"f({r['input']!r}): got {r['actual']!r}, expected {r['expected']!r}"
                for r in failed
            )
            prompt += (
                "\n\nThis candidate failed the shown examples:\n" + candidate +
                "\nFailures:\n" + details +
                "\nReconsider the entire rule and return corrected code."
            )
        except api.BudgetExceeded:
            break
    return code
