import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Infer the simplest rule that explains ALL examples; verify it by hand on each example before answering.",
    "Consider pairwise/adjacent operations, windows (size 2 or 3), prefix sums, index-dependent rules, and filtering; output length may differ from input length. Compare output length to input length to infer window size.",
    "Avoid overfitting: no hardcoded lookups of example inputs; handle empty lists and edge cases gracefully.",
    "The code must define exactly `def f(xs):` at top level, with any imports included, and must return a list of ints.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for b in reversed(blocks):
        if re.search(r"def\s+f\s*\(", b):
            return b
    if blocks:
        return blocks[-1]
    return text


def has_f(code):
    return re.search(r"def\s+f\s*\(", code) is not None


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    prompt = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "First briefly state the rule in one or two sentences and test it against several examples "
        "(including output length vs input length), "
        "then give the final code in one ```python block. Keep the reply concise and always finish with the code block."
    )
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not has_f(code):
            prompt += "\n\nYour previous reply had no `def f(xs):` code block. Reply with the rule in one sentence and the full code block."
            continue
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
