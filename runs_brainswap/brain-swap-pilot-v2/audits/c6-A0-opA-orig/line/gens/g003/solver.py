"""Seed solver, generation 3: reason briefly, then repair against check feedback."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the exact rule, paying close attention to output length, sign of values, "
    "empty lists and off-by-one indexing."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Work out how the output length relates to the input length before choosing a rule.",
    "Check how negative and zero values are treated; the rule may differ for them.",
    "Verify your rule by hand on every example before answering.",
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
        + "First give a short reasoning paragraph about the rule, then return the code "
        "in one ```python block."
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
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        ]
        prompt = (
            "Your previous function was wrong on some examples:\n"
            + "\n".join(lines)
            + "\n\nRe-derive the rule from all examples (not just these), then return "
            "a corrected full function in one ```python block.\n\n"
            + shown
        )
    return code
