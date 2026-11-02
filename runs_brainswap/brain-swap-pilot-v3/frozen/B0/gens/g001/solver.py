"""Infer a list transformation from examples and verify the proposed code."""

import re

SYSTEM = (
    "You are an expert at inferring concise, general Python list transformations. "
    "Infer the underlying rule, not just a pattern that happens to fit the examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']}) == {ex['output']}" for ex in task["examples"]
    )
    prompt = (
        "Infer a general rule for def f(xs), mapping a list of integers to a list "
        "of integers. All examples must be satisfied:\n" + shown + "\n\n"
        "Before writing code, reason carefully about competing simple rules. "
        "In particular, distinguish filtering values from filtering positions, "
        "and consider adjacent pairs, runs, indices, parity, signs, and arithmetic "
        "transformations. Check every output element and its ordering against every "
        "example. Prefer a simple rule that explains all examples, including empty "
        "outputs, rather than a coincidental numerical relationship. Handle short "
        "and empty lists and avoid mutating the input. "
        "Return the final function in a single Python code block."
    )
    code = ""
    for attempt in range(3):
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
            "\n\nThe following proposed code failed the shown examples:\n```python\n"
            + code + "\n```\n" + details
            + "\nReconsider the rule from scratch, check all examples, and return "
            "a corrected function in one Python code block."
        )
    return code
