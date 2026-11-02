"""Solver v2: check-driven repair loop with full-history feedback."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the exact rule, test it by hand against every example, then code it. "
    "Prefer simple, general rules over special cases."
)
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Common patterns: filter, map each element, adjacent/pairwise differences or sums, "
    "running totals, index-dependent rules, sorting, counting, or reversing.",
    "Empty input must give the right empty-type output. Negative numbers are common.",
]


def extract(text):
    v0 = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return v0[-1] if v0 else text


def build_prompt(task):
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
    base = build_prompt(task)
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
            results = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in results if not r["passed"]]
        if not failed:
            return code
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:4]
        ]
        prompt = (
            base
            + f"\n\nYour previous attempt was:\n```python\n{code}\n```\n"
            + "It failed:\n"
            + "\n".join(lines)
            + "\n\nThe rule you guessed is wrong. Re-derive the rule from the examples, "
            "check it against every example, and return the full corrected code in one ```python block."
        )
    return code
