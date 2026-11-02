"""Example-driven Python function synthesizer."""
import re

SYSTEM = (
    "You are an expert at inferring precise list transformations from examples. "
    "Distinguish a rule that explains all examples from coincidental patterns."
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
        "Infer the intended general rule for f, which maps a list of integers to "
        "a list of integers. All examples are exact:\n" + examples + "\n\n"
        "First reason briefly about several plausible rules. Examine which input "
        "positions contribute to each output, ordering, filtering, arithmetic, "
        "adjacent pairs or windows, and whether the output length is informative. "
        "Reject hypotheses that fail even one example. Prefer a simple uniform "
        "rule rather than special cases. Consider empty and short inputs, repeated "
        "values, negative numbers, ties, and Python indexing boundaries. "
        "Then give the complete standard-library-only Python implementation as "
        "the final fenced code block, defining def f(xs). Do not hardcode examples."
    )
    code = ""
    feedback = ""
    for _ in range(3):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
            candidate = extract(reply)
            code = candidate
            if api.budget().get("checks", 0) <= 0:
                return code
            report = api.check(candidate)
            failed = [r for r in report if not r["passed"]]
            if not failed:
                return candidate
            feedback += (
                "\n\nYour previous implementation:\n```python\n" + candidate
                + "\n```\nfailed these examples:\n"
                + "\n".join(
                    f"f({r['input']!r}) returned {r['actual']!r}; "
                    f"expected {r['expected']!r}"
                    for r in failed
                )
                + "\nReconsider the rule and return a corrected complete function."
            )
        except api.BudgetExceeded:
            break
    return code
