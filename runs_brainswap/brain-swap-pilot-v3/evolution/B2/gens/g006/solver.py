"""Example-driven Python function synthesis."""

import re

SYSTEM = (
    "You infer small deterministic list transformations from examples. "
    "Favor simple rules that explain every input and output, including ordering, "
    "filtering, duplicates, boundaries, and negative numbers."
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
        "Infer the intended general rule for a Python function f(xs), which takes "
        "a list of integers and returns a list of integers.\n\n"
        + shown
        + "\n\nFirst reason carefully about how every output is produced. Consider "
        "elementwise transforms, filters, adjacent pairs or triples, indices, "
        "arithmetic, parity, signs, and combinations of these. Align outputs to "
        "inputs and check all examples, especially output lengths and ordering. "
        "Distinguish plausible competing rules and prefer the simplest rule that "
        "explains all examples rather than memorizing them. Handle empty and short "
        "inputs naturally. Then return the implementation in a single Python code "
        "block defining def f(xs). Use only the standard library."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if candidate:
            code = candidate
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            "\n\nThe previous implementation was:\n```python\n"
            + code + "\n```\nIt failed these examples:\n" + details
            + "\nReconsider the underlying rule and return a corrected complete "
            "implementation in a Python code block."
        )
    return code
