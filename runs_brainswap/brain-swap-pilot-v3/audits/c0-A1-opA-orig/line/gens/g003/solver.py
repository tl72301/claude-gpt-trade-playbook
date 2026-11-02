import re

SYSTEM = "You write small, correct Python functions from input/output examples. Think about the rule carefully before coding."
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Infer the rule from ALL examples; verify each example by hand before answering.",
    "Output length may differ from input length (windows, pairs, filtering, prefix sums, etc.).",
    "Consider: sliding windows, adjacent pairs, running totals/min/max, counting, filtering by condition then mapping.",
    "Handle edge cases such as empty or short lists without raising exceptions.",
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
        + "Briefly state the rule you infer first, then give the code in one ```python block."
    )
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return code
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return code
        first = failed[0]
        prompt += (
            f"\n\nAttempt {attempt + 1} was wrong ({len(failed)} of {len(report)} examples failed): "
            f"f({first['input']}) returned {first['actual']}, expected {first['expected']}. "
            "Reconsider the rule from scratch, then give fixed code."
        )
    return code
