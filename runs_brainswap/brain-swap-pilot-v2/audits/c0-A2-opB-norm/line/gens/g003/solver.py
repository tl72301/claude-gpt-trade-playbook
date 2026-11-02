"""Infer list transformations from examples and check the resulting code."""

import re

SYSTEM = (
    "You infer simple Python list transformations from examples. "
    "Preserve ordering and duplicates, and reason carefully about boundaries."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    pos = text.find("def f(")
    return text[pos:].strip() if pos >= 0 else text.strip()


def solve(task, api):
    examples = "\n".join(
        "f(%r) == %r" % (item["input"], item["output"])
        for item in task["examples"]
    )
    prompt = (
        "Infer the intended general transformation from all examples. Input and "
        "output are lists of integers. Do not memorize the examples.\n\n"
        + examples
        + "\n\nConsider short pipelines involving filtering, mapping, indexing, "
        "adjacent elements and ordering. Distinguish indices in the original "
        "list from indices after filtering; also consider filtering before versus "
        "after mapping. Check whether output numbers are values, transformed "
        "values, indices, counts, or remainders. Compare plausible rules on every "
        "example, including duplicates. Prefer a simple consistent rule, but "
        "avoid inventing thresholds or special cases unsupported by evidence. "
        "Handle empty lists, zero, negative numbers and boundaries naturally. "
        "Return only complete Python code defining def f(xs) in a fenced block."
    )
    try:
        code = extract(api.llm(prompt, system=SYSTEM))
    except api.BudgetExceeded:
        return "def f(xs):\n    return []"

    # Independent review targets hidden-test ambiguities, not just example fit.
    try:
        review = (
            "Independently infer the simplest transformation supported by these "
            "examples, then compare it with the proposed code. Trace each output "
            "to its source. Consider competing operation orders, original versus "
            "filtered indices, strict versus inclusive comparisons, and Python "
            "behavior for zero and negative values. Do not change a supported "
            "rule merely to speculate; fix mistakes and unnecessary special cases.\n\n"
            + examples
            + "\n\nProposed code:\n```python\n"
            + code
            + "\n```\n\nReturn only complete Python code defining def f(xs) "
            "in a fenced block."
        )
        revised = extract(api.llm(review, system=SYSTEM))
        if "def f(" in revised:
            code = revised
    except api.BudgetExceeded:
        pass

    while True:
        try:
            if api.budget().get("checks", 0) <= 0:
                break
            results = api.check(code)
        except api.BudgetExceeded:
            break
        failures = [item for item in results if not item["passed"]]
        if not failures:
            break
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            repair = (
                "This code fails visible examples. Infer a simple general rule "
                "that explains every example; do not use a lookup table.\n\n"
                + examples
                + "\n\nCode:\n```python\n"
                + code
                + "\n```\n\nFailures:\n"
                + "\n".join(
                    "input=%r expected=%r actual=%r"
                    % (item["input"], item["expected"], item["actual"])
                    for item in failures
                )
                + "\n\nReturn only complete Python code defining def f(xs) "
                "in a fenced block."
            )
            revised = extract(api.llm(repair, system=SYSTEM))
            if "def f(" not in revised or revised == code:
                break
            code = revised
        except api.BudgetExceeded:
            break
    return code
