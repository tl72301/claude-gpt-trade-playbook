"""Synthesize a list-to-list function from examples."""

import re

SYSTEM = (
    "You infer compact Python programs from examples. "
    "Generalize the generating rule rather than memorizing examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({example['input']!r}) == {example['output']!r}"
        for example in task["examples"]
    )
    prompt = (
        "Infer the simplest plausible rule shared by ALL examples for "
        "`def f(xs):`, mapping a list of integers to a list of integers.\n"
        + examples
        + "\n\nBefore coding, compare plausible rules against every example. "
        "Consider whether outputs represent values, transformed values, positions, "
        "counts, or results from adjacent elements or groups. Check order, duplicates, "
        "negative numbers, zero, and strict versus inclusive boundaries. Avoid "
        "assuming conditions that the examples do not establish. Prefer a coherent, "
        "simple rule over arbitrary exceptions. Handle empty and short inputs. "
        "Return the final function in a Python code block."
    )
    best = ""
    best_passed = False
    previous = ""
    feedback = ""

    for attempt in range(2):
        try:
            budget = api.budget()
            if budget.get("llm_calls", 0) <= 0:
                break
            query = prompt
            if attempt:
                query += (
                    "\n\nReview this candidate independently for an incorrect "
                    "inferred rule, especially ambiguity at boundaries or positional "
                    "conditions. Compare alternative explanations with all examples. "
                    "Keep it if it is already the simplest well-supported rule; "
                    "otherwise correct it.\nCandidate:\n```python\n"
                    + previous
                    + "\n```\n"
                    + feedback
                    + "\nReturn the complete final function in a Python code block."
                )
            candidate = extract(api.llm(query, system=SYSTEM))
        except api.BudgetExceeded:
            break

        if not candidate:
            continue
        previous = candidate
        checked = False
        failures = []
        try:
            if api.budget().get("checks", 0) > 0:
                results = api.check(candidate)
                checked = True
                failures = [result for result in results if not result["passed"]]
        except api.BudgetExceeded:
            pass
        except Exception as exc:
            checked = True
            failures = [{"input": None, "expected": None, "actual": repr(exc)}]

        if checked and not failures:
            best = candidate
            best_passed = True
            feedback = "The candidate passes the shown examples."
        elif checked:
            feedback = "The candidate fails shown examples:\n" + "\n".join(
                f"input={r['input']!r}, expected={r['expected']!r}, "
                f"actual={r['actual']!r}"
                for r in failures[:5]
            )
            if not best:
                best = candidate
        else:
            feedback = "The candidate was not checked."
            if not best_passed:
                best = candidate

    return best
