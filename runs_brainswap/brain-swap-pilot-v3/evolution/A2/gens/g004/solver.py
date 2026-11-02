import re

SYSTEM = "You write small, correct Python functions from input/output examples. Think about the rule step by step before coding."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Outputs are often shorter than inputs (e.g. pairwise/windowed ops over adjacent elements, length n-1 or n-2). Work out the window size and the operation (sum, diff, compare, count, mod) from the examples.",
    "Verify your hypothesis by hand against EVERY example before answering, including empty-output cases.",
    "The code must define exactly `def f(xs):` at top level and use only the standard library.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        for b in reversed(blocks):
            if "def f" in b:
                return b
        return blocks[-1]
    return text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    prompt = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Briefly state the rule, then give the code in one ```python block."
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
            f"\n\nAttempt {attempt + 1} was wrong: f({first['input']}) returned "
            f"{first['actual']}, expected {first['expected']}. Reconsider the rule "
            "from scratch and fix it. Return the full function in one ```python block."
        )
    return code
