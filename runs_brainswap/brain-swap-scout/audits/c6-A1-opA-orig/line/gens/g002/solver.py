"""Solver generation 2: rule-first prompting plus a check-driven repair loop."""

import re

SYSTEM = "You write small, correct Python functions from input/output examples."
ATTEMPTS = 3
USE_CHECK = True
HINTS = []


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        for block in reversed(blocks):
            if "def f" in block:
                return block
        return blocks[-1]
    return text


def _score(report):
    return sum(1 for r in report if r.get("passed"))


def _feedback(report, limit=4):
    lines = []
    for r in [r for r in report if not r.get("passed")][:limit]:
        lines.append(
            f"f({r.get('input')}) returned {r.get('actual')}, expected {r.get('expected')}"
        )
    return "\n".join(lines)


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "First, in one or two sentences, state the single transformation rule that "
        "explains ALL examples. Verify the rule by hand against several examples, paying "
        "attention to empty lists, negative numbers, zeros, and output length. "
        "Then return the code in one ```python block."
    )
    prompt = base
    best_code, best_score = "", -1
    previous = ""
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except Exception:
            break
        code = extract(reply)
        if not code.strip():
            continue
        if not USE_CHECK:
            return code
        try:
            report = api.check(code)
        except Exception:
            report = []
        if report:
            score = _score(report)
            if score > best_score:
                best_code, best_score = code, score
            if score == len(report):
                return code
        else:
            if not best_code:
                best_code = code
        previous = code
        feedback = _feedback(report)
        prompt = (
            base
            + f"\n\nPrevious attempt:\n```python\n{previous}\n```\n"
            + (f"It failed these examples:\n{feedback}\n" if feedback else
               "It did not run correctly on the examples.\n")
            + "Re-derive the rule from all examples and return a corrected ```python block."
        )
    return best_code or previous
