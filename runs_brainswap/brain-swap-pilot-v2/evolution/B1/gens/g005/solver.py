"""Example-driven Python function synthesis."""

import ast
import re

SYSTEM = (
    "You infer Python transformations from examples. Seek the simplest "
    "general rule supported by all examples; never memorize the examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[^\S\n]*\n(.*?)```", text, re.I | re.S)
    for choice in list(reversed(blocks)) + [text]:
        code = choice.strip()
        try:
            tree = ast.parse(code)
            if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "f"
                   for n in tree.body):
                return code
        except SyntaxError:
            continue
    return ""


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer and implement def f(xs), returning a list of ints. Examples:\n"
        + shown +
        "\n\nWork systematically. First examine output lengths and align outputs "
        "with inputs, indices, adjacent pairs, or selected positions. Test "
        "candidate rules numerically against EVERY output, including duplicates "
        "and negative values. Consider filters, maps, neighbors and windows, "
        "runs, positional and value-based conditions, cumulative state, counts, "
        "aggregates, extrema, divisibility and remainders. A constant-looking "
        "output may encode several related statistics or a repeated aggregate. "
        "For cumulative-looking outputs distinguish sums, counts, differences "
        "and state updates, including when the state is emitted. Compare multiple "
        "simple hypotheses that fit all examples and prefer the one requiring "
        "the fewest unsupported assumptions. Handle empty and short inputs "
        "naturally. Do not hardcode examples. Return only complete Python code "
        "in a fenced block."
    )
    candidates = []
    previous = ""
    feedback = ""
    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            if attempt == 0:
                request = prompt
            elif feedback:
                request = (
                    prompt + "\n\nPrevious code:\n```python\n" + previous
                    + "\n```\nObserved mismatches:\n" + feedback
                    + "\nRethink the entire rule and verify every example. "
                    "Return a corrected complete implementation."
                )
            elif attempt == 1:
                request = (
                    prompt + "\n\nIndependently reconsider this candidate:\n```python\n"
                    + candidates[0][1] + "\n```\nLook for alternative rules that "
                    "also match all examples but generalize differently. Check "
                    "index versus value, order, duplicates, and boundaries. "
                    "Return the best-supported complete implementation."
                )
            else:
                alternatives = "\n\n".join(
                    "Candidate %d:\n```python\n%s\n```" % (i + 1, code)
                    for i, (_, code) in enumerate(candidates)
                )
                request = (
                    prompt + "\n\n" + alternatives +
                    "\nCompare these implementations against all examples. "
                    "If they differ, identify which assumptions are supported "
                    "and which are coincidences; choose the most natural general "
                    "rule. Return the complete implementation."
                )
            candidate = extract(api.llm(request, system=SYSTEM))
            if not candidate:
                continue
            previous = candidate
            if api.budget().get("checks", 0) <= 0:
                if not candidates:
                    candidates.append((-1, candidate))
                break
            report = api.check(candidate)
            failures = [r for r in report if not r["passed"]]
            candidates.append((len(report) - len(failures), candidate))
            feedback = "\n".join(
                f"f({r['input']!r}) returned {r['actual']!r}; expected {r['expected']!r}"
                for r in failures
            )
        except api.BudgetExceeded:
            break
        except Exception:
            continue

    if candidates:
        # Prefer the most recently reconsidered candidate only when it has
        # matched at least as many checked examples as the earlier ones.
        return max(enumerate(candidates), key=lambda x: (x[1][0], x[0]))[1][1]
    return previous or "def f(xs):\n    return []"
