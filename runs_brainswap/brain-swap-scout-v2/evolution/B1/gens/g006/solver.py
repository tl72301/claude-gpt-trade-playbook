"""Infer a list transformation from examples and verify candidate code."""

import re

SYSTEM = (
    "You infer small Python list transformations from examples. Prefer a simple, "
    "general rule that explains every example, not a lookup table or a special "
    "case for the shown inputs. Think carefully about order, duplicates, indices, "
    "negative numbers, ties, and empty inputs."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:def f\s*\(|from \w+ import |import \w+)", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended rule for f, which takes a list of integers and returns "
        "a list of integers. All examples come from one general algorithm.\n\n"
        + shown
        + "\n\nConsider several plausible rules, including positional and "
        "neighbor-based rules, counts, sorting, filtering, arithmetic and modular "
        "operations. Test your proposed rule against EVERY example, element by "
        "element. Avoid fitting arbitrary constants or memorizing examples. "
        "Implement the simplest rule that explains all examples, including sensible "
        "behavior on unseen inputs. Return your reasoning briefly, then complete "
        "Python code in a fenced block defining def f(xs). Standard library only."
    )
    best = ""
    best_passes = -1
    history = prompt
    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            reply = api.llm(history, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not code:
            continue
        try:
            if api.budget().get("checks", 0) <= 0:
                return best or code
            report = api.check(code)
        except api.BudgetExceeded:
            return best or code
        passes = sum(bool(r["passed"]) for r in report)
        if passes > best_passes:
            best, best_passes = code, passes
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        feedback = "\n".join(
            f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
            for r in failed
        )
        history += (
            "\n\nYour previous candidate was:\n```python\n" + code
            + "\n```\nIt failed these shown examples:\n" + feedback
            + "\nReconsider the underlying rule rather than patching individual "
            "examples. Verify the replacement against all examples. Return complete "
            "replacement code in a Python fenced block."
        )
    return best
