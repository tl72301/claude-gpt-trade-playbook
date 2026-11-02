import re

SYSTEM = "You write small, correct Python functions from input/output examples. Think about the pattern carefully."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Outputs are often shorter than inputs: consider sliding windows (pairs/triples of neighbors), adjacent differences, comparisons producing 0/1, or filtering then mapping.",
    "Check output length versus input length for every example to infer the window size or filter rule.",
    "The function must generalize to hidden inputs including empty or short lists; handle them without errors.",
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
        + "Briefly state the rule you infer (verify it against every example), then give the code in one ```python block."
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
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        first = failed[0]
        prompt += (
            f"\n\nAttempt {attempt + 1} code:\n```python\n{code}\n```\nwas wrong: f({first['input']}) returned "
            f"{first['actual']}, expected {first['expected']}. Rethink the rule and fix it."
        )
    return code
