"""Example-driven Python function synthesizer."""

import re

SYSTEM = (
    "You synthesize concise, correct Python functions from examples. "
    "Infer the underlying general rule rather than memorizing examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Write def f(xs): mapping a list of integers to a list of integers.\n"
        "Infer the simplest consistent general transformation from ALL examples:\n"
        f"{shown}\n\n"
        "Consider filtering, arithmetic transformations, positions, neighboring "
        "elements, ordering, duplicates, and combinations of these. Distinguish "
        "values from indices and carefully infer operation order, inclusive "
        "boundaries, and behavior on empty or short inputs. Compare plausible "
        "rules against every example before choosing. Do not hardcode examples. "
        "Return only executable Python code in a single python code block."
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
            return code
        details = "\n".join(
            f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            f"\n\nYour previous code:\n```python\n{code}\n```\n"
            f"It failed these examples:\n{details}\n"
            "Reconsider the rule and return corrected code only."
        )
    return code
