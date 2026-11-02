"""Infer and verify a general list transformation from examples."""

import re

SYSTEM = (
    "You infer general Python list transformations from examples. Prefer a simple "
    "rule that explains every example, not a rule that merely fits a few cases. "
    "Return executable Python using only the standard library."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = task.get("examples", [])
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in examples
    )
    prompt = (
        "Infer the deterministic rule for f(xs), where xs and the result are "
        "lists of integers. Here are ALL available examples:\n"
        f"{shown}\n\n"
        "Look for a compact rule that explains every output element and its "
        "position. Consider whole-list properties as well as elementwise and "
        "neighbor-based rules: filtering, indexing, ranks, counts, modular "
        "arithmetic, comparisons, running calculations, and combinations of "
        "these. Check negative values, duplicates, output length and ordering "
        "carefully. Avoid assumptions unsupported by the examples. Do not "
        "memorize examples or use task IDs. Handle empty and short inputs "
        "naturally. Return only a Python code block defining def f(xs)."
    )
    candidates = []
    failures = []

    def check(code):
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return None, ""
        failed = [r for r in report if not r.get("passed")]
        feedback = "\n".join(
            f"f({r.get('input')!r}): expected {r.get('expected')!r}, "
            f"got {r.get('actual')!r}"
            for r in failed
        )
        return not failed, feedback

    # Generate independent hypotheses before exposing either to the other.
    for extra in (
        "",
        "\n\nIndependently compare plausible competing rules. In particular, "
        "test whether an apparent pattern is coincidental by checking every "
        "position and every example. Choose the simplest consistent rule.",
    ):
        try:
            code = extract(api.llm(prompt + extra, system=SYSTEM))
        except api.BudgetExceeded:
            break
        passed, feedback = check(code)
        if passed is None:
            if not candidates:
                candidates.append(code)
            break
        if passed:
            candidates.append(code)
        else:
            failures.append((code, feedback))

    # Adjudicate alternatives, or use counterexamples to repair failed code.
    if candidates:
        choices = "\n\n".join(
            f"Candidate {i + 1}:\n```python\n{code}\n```"
            for i, code in enumerate(candidates)
        )
        request = (
            prompt + "\n\n" + choices
            + "\n\nThese candidates match the checked examples. Critically "
            "compare their underlying rules, not just their code. Identify "
            "where they would disagree on new inputs and choose the most "
            "natural rule supported by all examples. If they share an "
            "unjustified assumption, correct it. Return only the complete "
            "best function in a Python code block."
        )
    elif failures:
        code, feedback = failures[-1]
        request = (
            prompt + "\n\nThis candidate failed:\n```python\n" + code
            + "\n```\nCounterexamples:\n" + feedback
            + "\nReconsider the rule and return a corrected complete function."
        )
    else:
        return ""

    try:
        revised = extract(api.llm(request, system=SYSTEM))
    except api.BudgetExceeded:
        return candidates[0] if candidates else failures[-1][0]

    passed, _ = check(revised)
    if passed:
        return revised
    if candidates:
        return candidates[0]
    return revised
