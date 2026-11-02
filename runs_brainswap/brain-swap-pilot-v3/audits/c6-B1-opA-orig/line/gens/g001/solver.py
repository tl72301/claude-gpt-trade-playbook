import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Infer the simplest rule that explains ALL examples; verify it by hand on each example before answering.",
    "Consider pairwise/adjacent operations, windows, prefix sums, index-dependent rules, and filtering; output length may differ from input length.",
    "Avoid overfitting: no hardcoded lookups of example inputs; handle empty lists and edge cases gracefully.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    prompt = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "First briefly state the rule in one or two sentences and test it against several examples, "
        "then give the final code in one ```python block."
    )
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        first = failed[0]
        prompt += (
            f"\n\nAttempt {attempt + 1} code:\n```python\n{code}\n```\n"
            f"It was wrong: f({first['input']}) returned {first['actual']}, "
            f"expected {first['expected']}. Reconsider the rule from scratch and fix it."
        )
    return code
