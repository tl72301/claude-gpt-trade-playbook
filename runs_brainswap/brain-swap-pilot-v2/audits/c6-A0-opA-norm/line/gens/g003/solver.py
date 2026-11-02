"""Solver with check-driven repair. Keeps the harness contract.

solve(task, api) -> str: Python source defining def f(xs) -> list[int].
"""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the exact rule, then verify it by hand against every example before answering."
)
ATTEMPTS = 3
USE_CHECK = True
MAX_FEEDBACK = 6
HINTS = [
    "Compare the output length with the input length: same, one less (pairwise), or filtered.",
    "Check whether the rule depends on sign (negative, zero, positive), parity, or index position.",
    "Check whether each output element combines neighbours, the element and its index, or a running value.",
    "If the output is empty for some inputs, find the condition that produces the empty list.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    for b in reversed(blocks):
        if "def f" in b:
            return b
    if blocks:
        return blocks[-1]
    m = re.search(r"(def f\(.*)", text, re.DOTALL)
    return m.group(1) if m else text


def failure_text(results):
    bad = [r for r in results if not r["passed"]]
    lines = [
        f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
        for r in bad[:MAX_FEEDBACK]
    ]
    return "\n".join(lines), len(bad)


def base_prompt(task):
    examples = "\n".join(f"f({e['input']}) == {e['output']}" for e in task["examples"])
    return (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n"
        + examples
        + "\n\n"
        + "".join(f"Hint: {h}\n" for h in HINTS)
        + "Return only the code in one ```python block."
    )


def solve(task, api):
    prompt = base_prompt(task)
    best = ""
    code = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        best = code
        if not USE_CHECK:
            return code
        try:
            results = api.check(code)
        except api.BudgetExceeded:
            break
        text, nbad = failure_text(results)
        if nbad == 0:
            return code
        prompt = (
            base_prompt(task)
            + f"\n\nPrevious attempt:\n```python\n{code}\n```\n"
            + f"It failed {nbad} example(s):\n{text}\n"
            + "Find the rule that explains all examples, including the failures above, "
            + "and return a corrected f in one ```python block."
        )
    return best
