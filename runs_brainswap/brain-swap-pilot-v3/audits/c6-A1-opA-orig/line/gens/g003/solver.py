import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "You reason carefully about the hidden rule before coding."
)
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Many rules are windowed: output[i] depends on a sliding window of adjacent elements "
    "(pairs, triples, sums, differences, min/max), so output length may be shorter than input "
    "(len - k + 1). Check output length vs input length first.",
    "Other rules: prefix sums, running max/min, sorting, filtering by a predicate, counting. "
    "Test your hypothesis by hand on EVERY example before answering.",
    "The function must generalize to unseen inputs, including empty or short lists; never hardcode outputs.",
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
        + "First briefly state the rule you infer and verify it against the examples, "
        "then give the code in one final ```python block."
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
        except Exception:
            return code
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        first = failed[0]
        prompt += (
            f"\n\nAttempt {attempt + 1} was wrong: f({first['input']}) returned "
            f"{first['actual']}, expected {first['expected']}. "
            "Reconsider the rule from scratch (a simpler one may fit) and fix it."
        )
    return code
