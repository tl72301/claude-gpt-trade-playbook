import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Outputs are often shorter than inputs: look for windowed operations over adjacent pairs or triples (output length len(xs)-1 or len(xs)-2), or sliding-window sums, differences, comparisons, and mod operations.",
    "Before coding, compare each output element with the input elements at the same index and its neighbours, and find one rule that fits ALL examples. Check the rule by hand against every example.",
    "The function must be named f and handle short or empty lists without raising exceptions.",
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
        + "Briefly state the rule in one or two sentences, then give the code in one ```python block."
    )
    code = ""
    best, best_pass = "", -1
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if "def f" not in code:
            prompt += "\n\nYour reply had no `def f`. Return a complete function named f in a ```python block."
            continue
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        except Exception:
            continue
        npass = sum(1 for r in report if r["passed"])
        if npass > best_pass:
            best, best_pass = code, npass
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        first = failed[0]
        prompt += (
            f"\n\nAttempt {attempt + 1} was wrong: f({first['input']}) returned "
            f"{first['actual']}, expected {first['expected']}. Reconsider the rule "
            "from scratch against all examples, then fix it."
        )
    return best or code
