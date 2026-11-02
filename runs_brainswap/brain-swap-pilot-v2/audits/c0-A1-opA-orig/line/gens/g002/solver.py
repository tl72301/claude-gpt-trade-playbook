import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "First infer the exact rule that explains every example, check it against each "
    "example by hand, then write the code."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Check edge cases: empty lists, all-negative lists, repeated values.",
    "Output length may differ from input length; derive the length rule from the examples.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block."
    )
    prompt = base
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
        details = "\n".join(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        )
        prompt = (
            base
            + "\n\nA previous attempt was:\n```python\n" + code + "\n```\n"
            + "It failed on:\n" + details + "\n"
            + "Find the rule error this reveals, then return the full corrected function "
            + "in one ```python block."
        )
    return code
