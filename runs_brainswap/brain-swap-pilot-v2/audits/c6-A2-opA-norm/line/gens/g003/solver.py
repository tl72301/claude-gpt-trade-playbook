"""Solver generation 4: check-driven repair with best-attempt retention."""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the single general rule that explains every example; do not special-case inputs."
)
ATTEMPTS = 4
USE_CHECK = True
HINTS = [
    "Before coding, state the rule in one sentence and test it by hand on two examples.",
    "Check the output length and order against each example, not just the values.",
]
FALLBACK = "def f(xs):\n    return list(xs)\n"


def extract(text):
    if not isinstance(text, str):
        return FALLBACK
    v0 = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    code = v0[-1] if v0 else text
    if "def f" not in code:
        return FALLBACK
    return code


def build_prompt(task, previous=None, feedback=None):
    examples = "\n".join(
        f"f({ex['input']}) == {ex['output']}" for ex in task["examples"]
    )
    p = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n"
        + examples
        + "\n\n"
        + "".join(f"Hint: {h}\n" for h in HINTS)
        + "Return only the code in one ```python block."
    )
    if previous is not None and feedback:
        p += (
            "\n\nYour previous attempt:\n```python\n" + previous + "\n```\n"
            "It failed these examples:\n" + feedback +
            "\nFind the rule that fits ALL examples and return a corrected full function."
        )
    return p


def score_and_feedback(results):
    """Return (number passed, feedback text) from api.check results."""
    passed = 0
    lines = []
    for r in results or []:
        if not isinstance(r, dict):
            continue
        if r.get("passed"):
            passed += 1
        elif len(lines) < 3:
            lines.append(
                f"- f({r.get('input')}) returned {r.get('actual')}, "
                f"expected {r.get('expected')}"
            )
    return passed, "\n".join(lines)


def solve(task, api):
    best_code, best_score = None, -1
    previous, feedback = None, None
    for _ in range(ATTEMPTS):
        try:
            reply = api.llm(build_prompt(task, previous, feedback), system=SYSTEM)
        except api.BudgetExceeded:
            break
        except Exception:
            break
        code = extract(reply)
        if not USE_CHECK:
            return code
        try:
            results = api.check(code)
        except api.BudgetExceeded:
            if best_code is None:
                best_code = code
            break
        except Exception:
            if best_code is None:
                best_code = code
            break
        n_pass, feedback = score_and_feedback(results)
        if best_code is None or n_pass > best_score:
            best_code, best_score = code, n_pass
        if results and all(isinstance(r, dict) and r.get("passed") for r in results):
            return code
        previous = code
    return best_code if best_code is not None else FALLBACK
