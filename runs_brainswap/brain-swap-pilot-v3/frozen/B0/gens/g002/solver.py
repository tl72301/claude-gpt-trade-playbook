"""Infer a general list transformation from examples and verify the code."""

import re

SYSTEM = (
    "You are an expert at inferring Python list transformations from examples. "
    "Identify the simplest underlying rule, not merely code that fits the examples."
)


def extract(text):
    blocks = re.findall(
        r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE
    )
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']}) == {ex['output']}" for ex in task["examples"]
    )
    prompt = (
        "Infer a general rule for def f(xs), mapping a list of integers to a list "
        "of integers. Examples:\n" + shown + "\n\n"
        "Reason before coding. First determine what each output element corresponds "
        "to: an input element, an adjacent pair, a selected element's index, or a "
        "run or group. Align outputs in order with inputs, including repeated values "
        "and empty outputs. Consider filtering before transformation, comparisons "
        "with neighbors, sign changes, parity, divisibility, indices, differences, "
        "counts and lengths of runs. Check both elements of each pair and whether "
        "the first or last element is treated specially.\n"
        "Compare plausible rules against ALL examples, including examples that "
        "distinguish strict from non-strict comparisons, zero from negative values, "
        "and odd/even indices from odd/even values. Do not assume a rule just because "
        "it matches one example. Favor a compact, consistent rule over special cases. "
        "Think about how competing rules differ on unseen inputs and choose the "
        "most natural general rule. Handle empty and short lists without mutating "
        "the input. Return the final function in a single Python code block."
    )
    code = ""
    for _ in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if not candidate:
            continue
        code = candidate
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"f({r['input']}) returned {r['actual']}; expected {r['expected']}"
            for r in failed
        )
        prompt += (
            "\n\nThis proposal failed the examples:\n```python\n" + code
            + "\n```\n" + details
            + "\nReconsider the correspondence between inputs and outputs from "
            "scratch. Verify every example, then return a corrected function in "
            "one Python code block."
        )
    return code
