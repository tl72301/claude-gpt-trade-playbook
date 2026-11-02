"""Example-driven Python function synthesizer."""
import ast
import re


def extract(text):
    blocks = re.findall(
        r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE
    )
    options = list(reversed(blocks)) + [text]
    for option in options:
        code = option.strip()
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "f"
            for node in tree.body
        ):
            return code
    return ""


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    system = (
        "You infer exact deterministic Python list transformations from examples. "
        "Return executable Python source defining a top-level function f(xs)."
    )
    candidates = []

    def generate(prompt):
        try:
            return extract(api.llm(prompt, system=system))
        except api.BudgetExceeded:
            return ""

    def test(code):
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return None
        return [r for r in report if not r["passed"]]

    def add(code):
        if code and all(code != old[0] for old in candidates):
            candidates.append((code, test(code)))

    common = (
        "Infer a simple exact rule that explains ALL examples and generalizes. "
        "Never memorize input examples. Return only executable Python source "
        "defining def f(xs), preferably in a Python code block.\n\n"
        + examples
    )
    add(generate(
        common
        + "\n\nFirst determine output length and which input positions contribute. "
        "Consider filters and subsequences, adjacent or wider windows, and "
        "aggregates. For each value compare arithmetic, modulo, signs, counts, "
        "ranks, frequencies, and position-dependent rules. Python modulo and "
        "floor division apply to negative values. Check every example."
    ))
    add(generate(
        common
        + "\n\nIndependently enumerate competing hypotheses before choosing one. "
        "Consider global statistics and predicates as well as local transformations: "
        "counts of qualifying elements or windows, frequency and first/last "
        "occurrence, repeated output values, and modular arithmetic involving "
        "indices or aggregate values. Distinguish coincidental correlations. "
        "Trace the length and every output value against all examples."
    ))

    def details(code, failures):
        result = "\n```python\n" + code + "\n```"
        if failures is None:
            return result + "\nCheck unavailable."
        if not failures:
            return result + "\nMatches supplied examples only."
        return result + "\nFailures:\n" + "\n".join(
            f"input={r['input']!r}, expected={r['expected']!r}, "
            f"actual={r['actual']!r}"
            for r in failures
        )

    if candidates:
        add(generate(
            "Independently infer the intended transformation from the examples, "
            "then critically compare the implementations. Passing examples does "
            "not prove a rule: seek a simple rule explaining output length and "
            "every value without arbitrary constants or coincidences. Consider "
            "global counts, order and frequency, filtered windows, index-dependent "
            "arithmetic, and negative values. Resolve disagreements in favor of "
            "the most naturally supported rule. Handle empty and short inputs "
            "consistently. Return only Python source defining def f(xs).\n\n"
            + examples + "\n\nCandidates:\n"
            + "\n".join(details(code, failures) for code, failures in candidates)
        ))
    else:
        add(generate(common + "\nReturn a complete top-level function, not analysis."))

    passing = [code for code, failures in candidates if failures == []]
    if passing:
        return passing[-1]

    checked = [(code, failures) for code, failures in candidates if failures is not None]
    if checked:
        best_code, best_failures = min(checked, key=lambda item: len(item[1]))
        repair = generate(
            "Correct this implementation using every example and the reported "
            "failures. Infer a general simple transformation, not a lookup table. "
            "Consider output length, global and local counts, positions, arithmetic "
            "and boundaries. Return only complete Python source defining def f(xs).\n\n"
            + examples + "\n\nCandidate:\n" + details(best_code, best_failures)
        )
        if repair:
            failures = test(repair)
            if failures is not None and len(failures) < len(best_failures):
                return repair
        return best_code

    return candidates[-1][0] if candidates else ""
