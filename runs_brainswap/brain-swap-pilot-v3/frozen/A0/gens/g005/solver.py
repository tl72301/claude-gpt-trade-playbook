import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 5
USE_CHECK = True
HINTS = [
    "Outputs are often shorter than inputs (length n-1 or n-2): think pairwise/adjacent-window operations "
    "(differences, sums, comparisons, sign of difference) over consecutive elements, possibly with filtering.",
    "Check the output length against the input length for every example before choosing a rule; "
    "the rule must work on every example, including short lists and empty outputs.",
    "Values may be taken modulo some number (e.g. 18) or compared with a threshold; test such hypotheses on all examples.",
    "Output may be a filter then a map: e.g. keep only elements/pairs satisfying a condition (parity, sign, "
    "size threshold), then transform them. Empty outputs signal a filter; work out which inputs were dropped.",
    "Outputs of 0/1 or -1/0/1 are usually comparisons or signs of adjacent differences; outputs of 1 or 2 "
    "may be counts, or a step-size/bucket of the difference. Tabulate each adjacent pair against its output.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    prompt = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below. First, for the examples, tabulate "
        "each output element against the input elements that produce it (index alignment, "
        "adjacent pairs, windows). Propose a rule, verify it on EVERY example by hand, "
        "then give the code.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "End with the final code in one ```python block."
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
        lines = "; ".join(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        )
        prompt += (
            f"\n\nAttempt {attempt + 1} was wrong ({len(failed)} failing): {lines}. "
            "Do not patch; re-derive the rule from the tabulated pairs."
        )
    return code
