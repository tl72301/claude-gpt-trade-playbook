import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "The function is likely a composition of simple steps: windowed/pairwise ops, prefix sums, filtering, sorting, mapping.",
    "Output length may differ from input length (e.g. sliding windows give len-k+1 items, filters shorten).",
    "Verify your hypothesis against EVERY example by hand before answering; generalize beyond the examples (empty lists, negatives, duplicates).",
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
        + "Think briefly about the rule first, then give the code in one ```python block."
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
            f"\n\nAttempt {attempt + 1} was wrong ({len(failed)} of {len(report)} examples fail): "
            f"f({first['input']}) returned {first['actual']}, expected {first['expected']}. "
            "Reconsider the rule from scratch if needed. Fix it."
        )
    return code
