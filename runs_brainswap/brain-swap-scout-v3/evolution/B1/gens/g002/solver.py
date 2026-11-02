"""Example-driven Python function synthesizer."""
import re


def extract(text):
    blocks = re.findall(
        r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE
    )
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    system = "You infer exact deterministic Python list transformations from examples."
    candidates = []

    def generate(prompt):
        try:
            return extract(api.llm(prompt, system=system))
        except api.BudgetExceeded:
            return None

    def test(code):
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return None
        return [r for r in report if not r["passed"]]

    common = (
        "Infer a general deterministic list-processing rule from ALL examples. "
        "Do not hard-code examples. These examples may admit several rules; "
        "look for a simple exact rule, not an approximate pattern. Consider "
        "selection, position, adjacent and wider windows, counts, ranks, "
        "arithmetic, modulo, signs, duplicates, and boundary behavior. "
        "Trace every output element back to the input. Negative numbers obey "
        "Python's modulo and floor-division semantics. Return only Python "
        "source defining def f(xs), in a code block.\n\n" + examples
    )

    first = generate(common)
    if not first:
        return first or ""
    candidates.append((first, test(first)))

    second = generate(
        common
        + "\n\nIndependently derive the rule. Work systematically: identify "
        "what determines output length, then determine each output value. "
        "Test competing hypotheses against all examples before implementing."
    )
    if second:
        candidates.append((second, test(second)))

    def details(code, failures):
        result = "\n```python\n" + code + "\n```"
        if failures is None:
            return result + "\nCheck unavailable."
        if not failures:
            return result + "\nMatches all supplied examples."
        return result + "\nFailures:\n" + "\n".join(
            f"input={r['input']!r}, expected={r['expected']!r}, "
            f"actual={r['actual']!r}"
            for r in failures
        )

    review = (
        "Infer the intended rule independently from the examples, then critically "
        "compare the candidate implementations below. Passing examples is necessary "
        "but not sufficient: reject arbitrary constants, coincidental correlations "
        "and unsupported assumptions. Consider alternative simple rules and "
        "boundary cases. If candidates disagree, choose the rule best supported "
        "by all examples. Return only Python source defining def f(xs).\n\n"
        + examples + "\n\nCandidates:\n"
        + "\n".join(details(code, failures) for code, failures in candidates)
    )
    revised = generate(review)
    if revised:
        candidates.append((revised, test(revised)))

    passing = [(code, failures) for code, failures in candidates if failures == []]
    if passing:
        # Prefer the reviewed implementation when it has been verified.
        return passing[-1][0]

    checked = [(code, failures) for code, failures in candidates if failures is not None]
    if checked:
        best_code, best_failures = min(checked, key=lambda item: len(item[1]))
        repair = generate(
            "Fix the following function to match every example while inferring "
            "a simple general rule rather than memorizing inputs. Pay particular "
            "attention to output length, positions, arithmetic, and boundaries. "
            "Return only Python source defining def f(xs).\n\n"
            + examples + "\n\nCandidate and failures:\n"
            + details(best_code, best_failures)
        )
        if repair:
            repair_failures = test(repair)
            if repair_failures is None or len(repair_failures) < len(best_failures):
                return repair
        return best_code

    # If checks were unavailable, prefer the critically reviewed candidate.
    return candidates[-1][0]
