import re

SYSTEM = "You write small, correct Python functions from input/output examples. You reason carefully about the hidden rule and generalize beyond the examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Study the examples carefully. Outputs may be shorter than inputs; look at how the length relates to the input length (e.g. windows, pairs, filtering, prefix sums, running max/min, differences).",
    "Think of the simplest rule consistent with ALL examples, and verify it by hand on each example before answering. Handle empty and short lists.",
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
    best_code, best_pass = "", -1
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return code if not best_code else best_code
        except Exception:
            return code
        npass = sum(1 for r in report if r["passed"])
        if npass > best_pass:
            best_code, best_pass = code, npass
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        prompt += "".join(
            f"\n\nAttempt {attempt + 1} was wrong: f({r['input']}) returned "
            f"{r['actual']}, expected {r['expected']}."
            for r in failed[:3]
        ) + "\nRe-think the underlying rule from scratch if needed, then fix it."
    return best_code or code
