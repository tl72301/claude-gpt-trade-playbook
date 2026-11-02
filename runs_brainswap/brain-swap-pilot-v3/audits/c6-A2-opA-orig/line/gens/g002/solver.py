import re

SYSTEM = "You write small, correct Python functions from input/output examples. You reason carefully about the rule before coding."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Hidden tests include many inputs beyond the shown ones: lists of varying length, empty lists, negatives, duplicates. The rule must be general.",
    "Look for the rule by working out each output element from the input: consider adjacent pairs, windows, prefix sums, running max/min, filtering by index or value, sorting, and combinations (e.g. filter then map).",
    "Check the output length versus the input length: shorter outputs often mean pairwise/window ops or filtering.",
    "Verify your rule by hand against EVERY example before writing code. Do not hardcode examples.",
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
        + "First state the rule briefly in plain words, then give the code in one ```python block."
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
            if not best:
                best = code
            break
        npass = sum(1 for r in report if r["passed"])
        if npass > best_pass:
            best, best_pass = code, npass
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        first = failed[0]
        prompt += (
            f"\n\nAttempt {attempt + 1} was wrong:\n```python\n{code}\n```\n"
            f"f({first['input']}) returned {first['actual']}, expected {first['expected']}. "
            "Rethink the rule from scratch if needed, then give fixed code."
        )
    return best or code
