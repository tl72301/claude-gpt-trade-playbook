"""Seed solver, generation 2: rule-first prompting with check-driven repair."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "You infer the exact rule before writing code and verify it against every example."
)
ATTEMPTS = 3
USE_CHECK = True
HINTS = [
    "Compare each output element with the input at the same index, its neighbours, and prefixes or suffixes.",
    "Outputs can be shorter or longer than the input. Check lengths, empty lists, and negative numbers.",
    "Before answering, trace your code by hand on at least two examples.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if "def f" in block:
            return block
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "First state the rule in one or two sentences. Then return the code in one ```python block "
        "that defines f(xs)."
    )
    prompt = base
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if "def f" not in code:
            prompt = base + "\n\nYour last reply did not define a function named f. Define def f(xs) in a ```python block."
            continue
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
        prompt = (
            base
            + f"\n\nA previous attempt was:\n```python\n{code}```\n"
            + f"It was wrong: f({first['input']}) returned {first['actual']}, expected {first['expected']}. "
            + "Find the rule that explains all examples, then give a corrected ```python block."
        )
    return code

