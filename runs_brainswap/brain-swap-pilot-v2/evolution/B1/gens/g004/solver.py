"""Example-driven Python function synthesis."""

import ast
import re

SYSTEM = (
    "You infer precise transformations from input-output examples. Seek a single "
    "simple general algorithm that explains every example, not a memorized answer."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[^\S\n]*\n(.*?)```", text, re.I | re.S)
    choices = list(reversed(blocks)) + [text]
    for choice in choices:
        code = choice.strip()
        try:
            tree = ast.parse(code)
            if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "f"
                   for n in tree.body):
                return code
        except SyntaxError:
            pass
    return ""


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended algorithm and implement def f(xs), returning a list "
        "of ints. The examples are complete input/output pairs:\n\n" + shown +
        "\n\nFirst work out the role of each output and verify the entire sequence "
        "for every example. Consider filtering and mapping, adjacent pairs or "
        "windows, runs, prefix or cumulative state, indices, counts, extrema, "
        "sorting, divisibility and remainders, and combinations of these. "
        "For short outputs consider aggregate statistics as well as filtered "
        "elements. Compare competing explanations, especially ones that differ "
        "on duplicates, negatives, ties, ordering and boundaries. Prefer a "
        "simple consistent rule over an arbitrary coincidence. Do not hardcode "
        "the examples. Implement the general rule, including empty and short "
        "inputs. Return only Python code in a fenced block."
    )
    best = ""
    best_passed = -1
    previous = ""
    feedback = ""
    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            if not attempt:
                request = prompt
            elif feedback:
                request = (
                    prompt + "\n\nA previous implementation was:\n```python\n"
                    + previous + "\n```\nIts observed failures:\n" + feedback
                    + "\nReconsider the algorithm, not just individual cases. "
                    "Return a corrected complete implementation."
                )
            else:
                request = (
                    prompt + "\n\nA candidate fitting the examples is:\n```python\n"
                    + best + "\n```\nIndependently infer the rule again. Identify "
                    "plausible simpler alternatives and check all examples, including "
                    "the exact output length and order. Pay particular attention to "
                    "whether it assumes an unsupported boundary or tie behavior. "
                    "Retain the candidate if no alternative is better supported. "
                    "Return the complete implementation."
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
            # A malformed candidate or failed check should not discard a
            # previously checked implementation.
            continue
    return best or previous or "def f(xs):\n    return []"
