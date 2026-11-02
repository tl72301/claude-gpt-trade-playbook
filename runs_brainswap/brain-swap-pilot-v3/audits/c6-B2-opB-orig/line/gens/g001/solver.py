"""Example-based Python function synthesis."""

import re

SYSTEM = (
    "You infer simple, general list transformations from examples and write "
    "correct Python. Prefer rules that explain every example without special cases."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.I)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:from \w+ import .*\n|import .*\n|def f\()", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation from these examples and implement "
        "def f(xs), returning a list of integers.\n\n"
        + shown
        + "\n\n"
        "Reason carefully before coding: compare output lengths and ordering, "
        "and consider compositions of simple operations, not just one operation. "
        "Possible operations include filtering by value or index, arithmetic "
        "or modular transformations, adjacent differences, prefix sums, counts, "
        "deduplication, and sorting. Distinguish filtering before transformation "
        "from filtering afterward. Check your proposed rule against every example, "
        "including duplicates and negative numbers. Prefer a compact uniform rule "
        "that generalizes to empty and unseen inputs; do not memorize examples. "
        "Return the final implementation in one Python code block."
    )
    code = ""
    for attempt in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        try:
            compile(candidate, "<candidate>", "exec")
        except (SyntaxError, ValueError):
            prompt += "\nThe previous response was not valid Python. Return valid code."
            continue
        code = candidate
        if api.budget().get("checks", 0) <= 0:
            break
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        details = "\n".join(
            f"input {r['input']!r}: expected {r['expected']!r}, "
            f"got {r['actual']!r}"
            for r in failed
        )
        prompt += (
            "\n\nThis implementation failed the shown examples:\n```python\n"
            + code + "\n```\n" + details
            + "\nReconsider the entire rule, then return a corrected implementation."
        )
    return code
