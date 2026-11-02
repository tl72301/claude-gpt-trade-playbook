"""Example-based Python function solver."""

import re

SYSTEM = (
    "You infer concise, general Python list transformations from examples. "
    "Be meticulous about ordering, duplicates, indices, boundary cases, and "
    "the distinction between conditions on values and positions."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    return text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({e['input']!r}) == {e['output']!r}" for e in task["examples"]
    )
    prompt = (
        "Infer the intended general rule for a function f(xs) that takes a list "
        "of integers and returns a list of integers.\n\n"
        + examples
        + "\n\n"
        "First reason through all examples together. Consider whether the rule "
        "filters values, selects by index or neighbors, transforms values or "
        "indices, aggregates, or combines these operations. Check the exact "
        "output order and repeated elements. Compare plausible alternative "
        "rules, especially those that agree on only a few examples; prefer a "
        "simple rule that explains every example without special cases. "
        "Handle empty and short lists naturally. Do not memorize examples.\n"
        "Finally return the implementation in a single Python code block defining "
        "def f(xs). Use only the standard library."
    )
    best = "def f(xs):\n    return []\n"
    best_score = -1
    for attempt in range(3):
        try:
            text = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(text)
        if not re.search(r"(?m)^\s*def\s+f\s*\(", code):
            prompt += (
                "\nYour previous response did not define f. Return a Python "
                "code block containing a complete def f(xs)."
            )
            continue
        try:
            feedback = api.check(code)
        except api.BudgetExceeded:
            return code if best_score < 0 else best
        except Exception as exc:
            prompt += f"\nThe previous implementation could not be checked: {exc}. Fix it."
            continue
        score = sum(bool(r.get("passed")) for r in feedback)
        if score > best_score:
            best, best_score = code, score
        failures = [r for r in feedback if not r.get("passed")]
        if not failures:
            return code
        details = "\n".join(
            f"f({r.get('input')!r}) returned {r.get('actual')!r}; "
            f"expected {r.get('expected')!r}"
            for r in failures
        )
        prompt += (
            f"\n\nAttempt {attempt + 1}:\n```python\n{code}\n```\n"
            f"Failed shown examples:\n{details}\n"
            "Reconsider the underlying rule using all examples, then provide "
            "a corrected complete function in a Python code block."
        )
    return best
