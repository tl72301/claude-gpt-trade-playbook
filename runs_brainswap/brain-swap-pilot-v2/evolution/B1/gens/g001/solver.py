"""Example-driven Python function synthesis."""

import re

SYSTEM = (
    "You infer precise list transformations from examples and write robust Python. "
    "Prefer simple, uniform rules that explain every example, including duplicates, "
    "negative numbers, ordering, and boundary cases."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended general transformation from these examples, then write "
        "def f(xs) returning a list of ints.\n\n"
        + shown
        + "\n\nConsider several plausible rules before choosing. Check every output "
        "element against the examples. Pay special attention to whether the rule "
        "depends on values, indices, neighbors, frequencies, ordering, or arithmetic; "
        "distinguish similar rules using all examples. Handle empty and short lists, "
        "duplicates, and negative values naturally. Do not hardcode examples. "
        "Return only Python code in a fenced block."
    )
    best = ""
    best_passed = -1
    previous = ""
    feedback = ""
    for attempt in range(3):
        try:
            budget = api.budget()
            if budget.get("llm_calls", 0) <= 0:
                break
            if attempt == 0:
                request = prompt
            elif feedback:
                request = (
                    prompt + "\n\nPrevious code:\n```python\n" + previous
                    + "\n```\nIt failed these shown examples:\n" + feedback
                    + "\nReconsider the underlying rule and fix the code."
                )
            else:
                request = (
                    prompt + "\n\nA proposed solution is:\n```python\n" + best
                    + "\n```\nIndependently review its inferred rule. Look for "
                    "unjustified assumptions and alternative simpler rules that fit "
                    "ALL examples, especially boundary conditions. If its rule is "
                    "well supported, retain it; otherwise correct it. Return code only."
                )
            candidate = extract(api.llm(request, system=SYSTEM))
            if not candidate:
                continue
            previous = candidate
            if api.budget().get("checks", 0) <= 0:
                if not best:
                    best = candidate
                break
            report = api.check(candidate)
            failures = [r for r in report if not r["passed"]]
            passed = len(report) - len(failures)
            if passed > best_passed or (passed == best_passed and not failures):
                best, best_passed = candidate, passed
            feedback = "\n".join(
                f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
                for r in failures
            )
            if not failures and attempt >= 1:
                break
        except api.BudgetExceeded:
            break
        except Exception:
            if not best:
                best = previous
            break
    return best or "def f(xs):\n    return []"
