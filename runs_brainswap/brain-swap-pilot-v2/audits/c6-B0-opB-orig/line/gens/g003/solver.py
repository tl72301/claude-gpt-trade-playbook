"""Example-based Python function synthesizer."""

import ast
import re

SYSTEM = (
    "Infer the simplest general list transformation supported by the examples. "
    "Reason about indexing, order, duplicates, boundaries and negative numbers. "
    "Do not specialize to the examples."
)


def extract(text):
    """Prefer a parseable block defining f, even if commentary follows it."""
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    candidates = blocks + [text]
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            tree = ast.parse(candidate)
        except SyntaxError:
            continue
        if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == "f" for node in tree.body):
            return candidate
    # Recover unfenced code preceded or followed by prose when possible.
    for match in re.finditer(r"(?m)^def f\s*\(", text):
        lines = text[match.start():].splitlines()
        for end in range(len(lines), 0, -1):
            candidate = "\n".join(lines[:end])
            try:
                tree = ast.parse(candidate)
            except SyntaxError:
                continue
            if any(isinstance(node, ast.FunctionDef) and node.name == "f"
                   for node in tree.body):
                return candidate
    return text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer a Python function def f(xs) returning a list of ints.\n"
        "Examples:\n" + shown + "\n\n"
        "Explain the evidence briefly, then give the complete function in one "
        "Python code block. Account for every output and omission, including "
        "order and repeated values. Consider whether outputs are values, indices, "
        "remainders, counts, or arithmetic results. Compare elementwise rules "
        "with rules involving consecutive pairs or triples, runs, and neighbors. "
        "For arithmetic results consider both operand orders, absolute differences, "
        "and filtering before versus after transformation. Check strictness, "
        "indexing, edge positions, zero, and negative numbers. Prefer the simplest "
        "rule consistent with all examples; do not memorize the examples."
    )
    try:
        code = extract(api.llm(prompt, system=SYSTEM))
    except api.BudgetExceeded:
        return "def f(xs):\n    return []"

    report = None
    if api.budget().get("checks", 0) > 0:
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            pass

    failed = [r for r in report if not r["passed"]] if report is not None else []
    if api.budget().get("llm_calls", 0) > 0:
        feedback = ""
        if failed:
            feedback = "\nThe proposed code fails these examples:\n" + "\n".join(
                f"input {r['input']!r}: got {r['actual']!r}, expected {r['expected']!r}"
                for r in failed
            )
        review = (
            prompt + "\n\nProposed solution:\n```python\n" + code + "\n```\n"
            + feedback
            + "\nIndependently derive the rule from the examples before reviewing "
            "the proposal. Identify plausible competing rules and any assumptions "
            "the examples do not distinguish. Trace each proposed output to its "
            "source element or elements, including its position and order. Look "
            "particularly for adjacent operations, indices versus values, modular "
            "arithmetic, off-by-one errors, and restrictions not justified by the "
            "examples. Fix errors, but do not replace a consistent simple rule with "
            "a more complicated speculation. Return the complete function in a "
            "single Python code block."
        )
        try:
            revised = extract(api.llm(review, system=SYSTEM))
            if api.budget().get("checks", 0) > 0:
                revised_report = api.check(revised)
                if all(r["passed"] for r in revised_report):
                    return revised
                if report is not None and not failed:
                    return code
                if report is not None and sum(r["passed"] for r in revised_report) < sum(
                    r["passed"] for r in report
                ):
                    return code
            return revised
        except api.BudgetExceeded:
            pass
    return code
