"""Example-driven solver."""
import re

SYSTEM = (
    "You are an expert at inferring list transformations from examples. "
    "Prefer simple, general rules over memorization. Check every example carefully."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if blocks:
        return blocks[-1]
    match = re.search(r"(?m)^(?:def f\(|import |from )", text)
    return text[match.start():] if match else text


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation from these examples:\n"
        + shown
        + "\n\nThe function takes a list of integers and returns a list of integers. "
        "First reason about several plausible rules and use ALL examples to distinguish "
        "them. Pay particular attention to whether the rule combines operations: "
        "filtering elements, adjacent pairs or windows, then mapping values, differences, "
        "counts, signs, parity, or remainders. Output length and ordering are important. "
        "Do not assume an operation is applied to the original list if the examples "
        "suggest filtering comes first. Avoid fitting constants or special cases without "
        "evidence. Consider empty and short inputs, negatives and duplicates. "
        "Then give the simplest general rule and implement it in a final Python code "
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
            if api.budget().get("checks", 0) <= 0:
                break
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            break
        prompt += (
            "\n\nYour previous implementation:\n```python\n" + code + "\n```\n"
            "It failed these shown examples:\n"
            + "\n".join(
                f"f({r['input']!r}) produced {r['actual']!r}; expected {r['expected']!r}"
                for r in failed
            )
            + "\nReconsider the entire rule, not just these cases. Return corrected "
            "code in a final Python block."
        )
    return code
