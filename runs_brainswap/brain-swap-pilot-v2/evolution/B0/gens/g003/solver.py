"""Example-based Python function synthesizer."""

import re


SYSTEM = (
    "You are an expert at inferring compact algorithms from examples. "
    "Distinguish rules that merely fit the examples from rules that generalize."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^def f\s*\(", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended deterministic transformation from these examples. "
        "Input and output are lists of integers.\n\n"
        f"{shown}\n\n"
        "Think carefully before coding. Compare plausible simple rules against EVERY "
        "example, including output length, order, duplicates, negative numbers, and "
        "whether operations use values, indices, neighbors, counts, or the entire list. "
        "Prefer a single natural general rule rather than special cases or memorizing "
        "the examples. Consider edge cases such as empty and short lists. "
        "Briefly explain your reasoning, then give the complete standalone standard-library "
        "Python implementation as one fenced code block defining def f(xs)."
    )
    code = "def f(xs):\n    return []\n"
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
        failed = [r for r in report if not r.get("passed")]
        if not failed:
            return code
        details = "\n".join(
            f"Input {r.get('input')!r}: expected {r.get('expected')!r}, "
            f"got {r.get('actual')!r}"
            for r in failed
        )
        prompt += (
            f"\n\nYour previous implementation failed the examples:\n{details}\n"
            f"Previous implementation:\n```python\n{code}\n```\n"
            "Reconsider the underlying rule and return a corrected complete function."
        )
    return code
