"""Infer a list transformation from examples and validate generated code."""
import re

SYSTEM = (
    "You are an expert at inferring precise list transformations from examples. "
    "Prefer simple, general rules over memorization."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({e['input']}) == {e['output']}" for e in task["examples"]
    )
    prompt = (
        "Infer the intended rule for this list-of-integers transformation.\n"
        + examples
        + "\n\nFirst reason carefully about multiple plausible rules. Check output "
        "lengths, ordering, filtering, adjacent pairs or triples, runs, arithmetic, "
        "signs and parity where relevant. Distinguish similar rules using ALL "
        "examples, including empty outputs and boundary cases. Prefer the simplest "
        "consistent rule that generalizes to unseen inputs. Do not hard-code the "
        "examples. Then give a complete standard-library-only implementation of "
        "`def f(xs):` returning a list of ints, in a final Python code block."
    )
    code = ""
    try:
        code = extract(api.llm(prompt, system=SYSTEM))
    except api.BudgetExceeded:
        return code

    report = None
    try:
        report = api.check(code)
    except api.BudgetExceeded:
        return code

    failed = [r for r in report if not r["passed"]]
    if failed:
        feedback = "\n".join(
            f"f({r['input']}) returned {r['actual']!r}; expected {r['expected']!r}"
            for r in failed
        )
        followup = (
            prompt + "\n\nThe following implementation failed validation:\n```python\n"
            + code + "\n```\nFailures:\n" + feedback
            + "\nReconsider the rule and fix every failure. Return the complete "
            "corrected function in a Python code block."
        )
    else:
        followup = (
            prompt + "\n\nA candidate implementation is:\n```python\n" + code
            + "\n```\nIt passes the shown examples, but may have inferred the wrong "
            "rule. Independently inspect the examples for a simpler or more precise "
            "rule, especially window size, ordering, filters, and boundary behavior. "
            "Change the implementation only if the evidence supports it. Return the "
            "complete best function in a final Python code block."
        )
    try:
        revised = extract(api.llm(followup, system=SYSTEM))
    except api.BudgetExceeded:
        return code
    try:
        revised_report = api.check(revised)
        if all(r["passed"] for r in revised_report):
            return revised
        if not failed:
            return code
        if sum(r["passed"] for r in revised_report) > sum(r["passed"] for r in report):
            return revised
    except api.BudgetExceeded:
        return code if not failed else revised
    return code
