"""Example-driven Python function synthesizer."""

import re

SYSTEM = (
    "You infer the intended simple algorithm from examples. Prefer a compact, "
    "general rule over memorization. Pay close attention to order, indexing, "
    "negative numbers, ties, and boundary cases."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:from \S+ import .+\n|import .+\n|\s*\n)*def f\s*\(", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended deterministic transformation from these examples:\n"
        + examples
        + "\n\nFirst reason about several plausible simple rules, testing each against "
        "ALL examples. Consider elementwise operations, filtering, adjacent or "
        "fixed-size groups, counts, indices, arithmetic and modular arithmetic. "
        "Distinguish negative-number modulo from remainder, and check output length, "
        "ordering, duplicates, ties and incomplete groups. Choose the simplest rule "
        "that explains every example without hardcoding. Then give its implementation "
        "as the final Python code block defining def f(xs). Standard library only."
    )
    best = ""
    best_passed = -1
    feedback = ""
    for attempt in range(3):
        try:
            budget = api.budget()
            if budget.get("llm_calls", 0) <= 0:
                break
            if attempt == 0:
                request = prompt
            elif best_passed == len(task["examples"]):
                request = (
                    prompt + "\n\nA candidate that passes the shown examples is:\n```python\n"
                    + best + "\n```\nIndependently scrutinize its inferred rule. "
                    "Does another simpler rule explain the examples better? Look for "
                    "accidental fits and edge-case errors. If it is sound, retain it. "
                    "Return your final implementation in a Python code block."
                )
            else:
                request = (
                    prompt + "\n\nThis candidate failed shown examples:\n```python\n"
                    + best + "\n```\n" + feedback
                    + "\nReconsider the underlying rule, not just the failing cases. "
                    "Return a corrected implementation in a Python code block."
                )
            reply = api.llm(request, system=SYSTEM)
            code = extract(reply)
            if not code:
                continue
            if api.budget().get("checks", 0) <= 0:
                if not best:
                    best = code
                break
            report = api.check(code)
            passed = sum(bool(r["passed"]) for r in report)
            if passed >= best_passed:
                best, best_passed = code, passed
                failures = [r for r in report if not r["passed"]]
                feedback = "\n".join(
                    f"f({r['input']!r}): got {r['actual']!r}, expected {r['expected']!r}"
                    for r in failures[:5]
                )
            if best_passed == len(task["examples"]) and attempt >= 1:
                break
        except api.BudgetExceeded:
            break
        except Exception:
            if best:
                break
    return best or "def f(xs):\n    return []\n"
