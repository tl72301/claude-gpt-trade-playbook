"""Example-driven Python function synthesizer."""

import re

SYSTEM = (
    "You synthesize Python functions from input-output examples. "
    "Infer a simple general rule, including its exact boundaries and operation order."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Write def f(xs), mapping a list of integers to a list of integers.\n"
        f"Examples:\n{shown}\n\n"
        "Infer the simplest plausible rule consistent with ALL examples. First "
        "consider several candidate rules, then choose one. Pay special attention "
        "to whether selection uses original values or positions, and whether "
        "filtering occurs before or after arithmetic, reversing, or sorting. "
        "Check output order and duplicates. Compare strict and inclusive "
        "boundaries, especially at zero; do not assume an unobserved boundary "
        "is settled by the examples. Prefer ordinary simple operations over "
        "arbitrary constants or complicated exceptions. Handle empty and short "
        "lists. Do not hardcode examples.\n"
        "Return only executable Python code in one python code block."
    )
    code = ""
    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if not candidate:
            continue
        code = candidate
        try:
            if api.budget().get("checks", 0) <= 0:
                break
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            # An independent review can expose an ambiguous boundary or a
            # mistaken operation order even when all visible examples pass.
            if attempt == 0 and api.budget().get("llm_calls", 0) > 0:
                prompt += (
                    f"\n\nCandidate code:\n```python\n{code}\n```\n"
                    "This passes the examples. Independently review its rule "
                    "against all examples. Identify plausible alternative rules "
                    "and discriminating inputs, particularly zero, negatives, "
                    "duplicates, and short lists. Prefer the most natural simple "
                    "rule; do not change a correct rule merely to make a change. "
                    "Return the final executable code only."
                )
                continue
            return code
        details = "\n".join(
            f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            f"\n\nPrevious code:\n```python\n{code}\n```\n"
            f"Failed examples:\n{details}\n"
            "Reconsider the entire rule and return corrected code only."
        )
    return code
