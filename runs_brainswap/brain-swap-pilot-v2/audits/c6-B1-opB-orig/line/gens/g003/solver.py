"""Synthesize a list-to-list Python function from examples."""

import re

SYSTEM = (
    "You infer general Python list transformations from examples. "
    "Prefer simple, conventional rules and return executable standard-library Python."
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
        "Infer a general rule for f(xs), where input and output are lists of "
        "integers. The examples are observations, not a complete specification.\n\n"
        f"{shown}\n\n"
        "Privately compare multiple simple hypotheses that fit ALL examples. "
        "Account for every included and omitted item. Consider filters followed "
        "by transformations, index versus value outputs, original versus filtered "
        "indices, order and duplicates, neighbors, and cumulative operations. "
        "Distinguish sign tests, parity and divisibility; consider zero explicitly. "
        "For numerical transformations consider both arithmetic and integer "
        "division or remainder, including their behavior on negatives. Do not "
        "assume a boundary from values absent in the examples. If several rules "
        "fit, compare how they behave on short inputs, zero, negatives, duplicates "
        "and boundary values, and prefer the simplest conventional rule rather "
        "than an accidental fit. Handle empty inputs naturally. Never use a lookup "
        "table for the examples.\n"
        "Return only executable Python code defining f(xs), preferably in a "
        "Python code block."
    )
    best_code = ""
    best_passed = -1
    feedback = ""
    checked_solution = False

    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            code = extract(api.llm(prompt + feedback, system=SYSTEM))
            if not code:
                continue
            try:
                compile(code, "<candidate>", "exec")
            except SyntaxError as exc:
                feedback = (
                    f"\n\nThe previous code had a syntax error: {exc}. "
                    "Return a complete corrected function."
                )
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
                if checked_solution:
                    return best_code
                checked_solution = True
                best_code = code
                feedback = (
                    "\n\nThis candidate fits the shown examples:\n"
                    f"{code}\n"
                    "Critically reconsider its generalization. Look for a simpler "
                    "conventional rule also fitting every example, especially "
                    "where zero, boundaries, signs, or index origins are not "
                    "observed. Do not change the rule merely because an alternative "
                    "is possible; retain it unless there is a clear reason to "
                    "prefer another. Return the complete best function."
                )
            else:
                details = "\n".join(
                    f"input={r.get('input')!r}, expected={r.get('expected')!r}, "
                    f"actual={r.get('actual')!r}"
                    for r in failed
                )
                feedback = (
                    "\n\nThe preceding candidate failed shown examples:\n"
                    f"{details}\nCandidate:\n{code}\n"
                    "Reconsider the underlying rule and operation order. "
                    "Check all examples, then return a complete corrected function."
                )
        except api.BudgetExceeded:
            break
        except Exception:
            break

    return best_code or "def f(xs):\n    return []\n"
