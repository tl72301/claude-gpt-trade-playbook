"""Synthesize a list-to-list Python function from examples."""

import re

SYSTEM = (
    "You infer concise, general Python list transformations from examples. "
    "Do not memorize examples. Return executable standard-library Python."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return (blocks[-1] if blocks else text).strip()


def solve(task, api):
    examples = task.get("examples", [])
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in examples
    )
    prompt = (
        "Infer the most plausible general rule for def f(xs), where xs and the "
        "result are lists of integers.\n\n"
        f"{shown}\n\n"
        "First reason privately about multiple simple rules that fit ALL examples. "
        "Consider filtering versus transforming, values versus indices, original "
        "versus filtered indices, order and duplicates, neighboring elements, "
        "cumulative state, and whether operations are composed. Use negative, "
        "zero, and repeated values as evidence; do not infer boundaries from "
        "unobserved cases without justification. Prefer simple rules over "
        "coincidental numerical patterns. Check your proposed rule against every "
        "element of every example, including omitted elements. Handle empty and "
        "short inputs naturally. Examples alone may be ambiguous: choose a "
        "plausible generalization, not a lookup table.\n"
        "Return only executable code in a Python code block defining f(xs)."
    )
    best_code = ""
    best_passed = -1
    feedback = ""

    for attempt in range(3):
        try:
            budget = api.budget()
            if budget.get("llm_calls", 0) <= 0:
                break
            reply = api.llm(prompt + feedback, system=SYSTEM)
            code = extract(reply)
            if not code:
                continue
            if not best_code:
                best_code = code

            if api.budget().get("checks", 0) <= 0:
                break
            report = api.check(code)
            passed = sum(bool(r.get("passed")) for r in report)
            if passed > best_passed:
                best_passed, best_code = passed, code
            failed = [r for r in report if not r.get("passed")]
            if not failed:
                return code

            details = "\n".join(
                f"input={r.get('input')!r}, expected={r.get('expected')!r}, "
                f"actual={r.get('actual')!r}"
                for r in failed
            )
            feedback = (
                "\n\nThe preceding candidate failed shown examples:\n"
                f"{details}\nCandidate:\n{code}\n"
                "Reconsider the underlying rule, including operation order and "
                "index/value distinctions. Verify all examples, then return a "
                "complete corrected function."
            )
        except api.BudgetExceeded:
            break
        except Exception:
            break

    return best_code or "def f(xs):\n    return []\n"
