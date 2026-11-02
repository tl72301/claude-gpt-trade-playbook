"""Example-based Python function synthesizer."""

import re

SYSTEM = (
    "You are an expert at inferring small list-processing programs from examples. "
    "Infer the simplest general rule that explains every example, not a lookup table. "
    "Consider filtering, adjacent pairs, runs, indices, signs, parity, and ordering. "
    "Be precise about boundaries, ties, negative numbers, and empty inputs."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^def f\s*\(", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation from ALL these examples. "
        "Before coding, compare plausible rules and check them against every example. "
        "Prefer a simple general algorithm; do not hardcode the examples. "
        "Handle empty and short lists and boundary cases naturally.\n\n"
        + examples
        + "\n\nReturn only Python code defining def f(xs), in a Python code block."
    )
    best = ""
    best_passed = -1
    previous = ""
    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        previous = code
        try:
            if api.budget().get("checks", 0) <= 0:
                return best or code
            report = api.check(code)
        except api.BudgetExceeded:
            return best or code
        passed = sum(bool(r["passed"]) for r in report)
        if passed > best_passed:
            best, best_passed = code, passed
        failures = [r for r in report if not r["passed"]]
        if not failures:
            return code
        feedback = "\n".join(
            f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
            for r in failures
        )
        prompt += (
            "\n\nYour previous code:\n```python\n" + previous + "\n```\n"
            "It fails these examples:\n" + feedback
            + "\nReconsider the rule from scratch, including output length and order. "
            "Return a corrected complete function in a Python code block."
        )
    return best or previous
