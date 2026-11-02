import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "The outputs are often derived from adjacent pairs, windows, or filtered elements of the input; infer the rule carefully from ALL examples, including output length relative to input length.",
    "Handle edge cases such as short lists (return []).",
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
        + "Briefly state the rule you infer, then give the code in one ```python block."
    )
    code = ""
    best, best_pass = "", -1
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        try:
            report = api.check(code)
        except Exception:
            return best or code
        npass = sum(1 for r in report if r["passed"])
        if npass > best_pass:
            best, best_pass = code, npass
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        first = failed[0]
        prompt += (
            f"\n\nAttempt {attempt + 1} was wrong: f({first['input']}) returned "
            f"{first['actual']}, expected {first['expected']}. Rethink the rule and fix it."
        )
    return best or code
